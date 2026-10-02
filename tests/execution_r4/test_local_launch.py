"""Approved local configuration reaches Core through manually owned dispatch."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from nexus_connector_core import CoreError, ShutdownPolicy

from okto_nexus.application.execution_local_launch import ApprovedLocalLaunch
from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
from okto_nexus.application.execution_leases import ExecutionChannel, ExecutionLeaseService
from okto_nexus.adapters.outbound.execution.embedded import EmbeddedExecutor
from okto_nexus.adapters.inbound.http import runtime_v1
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.base import iso_plus
from okto_nexus.errors import OktoNexusError
from test_local_realization import local_setup, publish
from test_binding_operator import prepare_operator
from test_vertical_inventory import _NativeFactory


@pytest.fixture
def admitted_local(local_setup, monkeypatch):
    deps, app, client, headers, body, candidate, root = local_setup
    # This boundary test sends manually. Stop the real automatic sender before
    # admitting anything so it cannot consume or refuse this test's operation.
    dispatch = app.state.embedded_dispatch_owner
    assert dispatch.pump is not None
    client.portal.call(dispatch.pump.stop)
    first = publish(local_setup, changes={"secret_bindings":{"OPENAI_API_KEY":"provider:LOCAL_TEST_KEY"}})
    assert first.status_code == 201, first.text
    view = first.json()
    _, apply = prepare_operator(client, headers, dict(client_intent_id="launch-binding", agent_id_hint="subject",
        executor_id=view["executor_id"], adapter_id=body["adapter_id"], candidate_ref=body["candidate_ref"],
        inventory_revision=body["inventory_revision"], realization_ref=view["realization_ref"],
        workspace_id=view["workspace_id"], alias="launch-assistant"))
    response = client.post("/v1/connections/bindings:apply", json=apply, headers=headers["operator"])
    assert response.status_code == 200, response.text
    binding = response.json()
    grant = client.post("/api/v1/harness/grants", headers=headers["operator"], json={
        "actor_agent_id":"subject", "endpoint_id":binding["endpoint_id"],
        "actions":["open","send","close"], "max_executions":3,
        "expires_at":iso_plus(deps.clock.now_iso(),600)})
    assert grant.status_code == 200, grant.text
    # This fixture explicitly qualifies only the selection/lease/Core boundary.
    # Automatic embedded dispatch and provider qualification are separate work.
    assert runtime_v1.protocol_info()["remote_execution_ready"]
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY' WHERE kind='embedded'")
    resolved = client.post("/v1/runtime/intents:resolve", headers=headers["subject"], json={
        "client_intent_id":"local-open", "intent":"runtime.start", "binding_id":binding["binding_id"],
        "workspace_binding_id":binding["workspace_binding_id"], "new_session":True})
    assert resolved.status_code == 200, resolved.text
    resolution = resolved.json()
    assert resolution["can_submit"], resolution
    admitted = client.post("/v1/runtime/operations", headers=headers["subject"], json={
        k:resolution[k] for k in ("client_intent_id","operation_id","resolution_revision","intent_hash")})
    assert admitted.status_code == 202, admitted.text
    owner = app.state.embedded_inventory_owner
    channel = ExecutionChannel(owner.key.server_id,owner.key.executor_id,owner.dispatcher.owner_id,owner.generation)
    access = build_execution_access(deps)
    reserved = reserve_execution_dispatch(deps.connection_factory,server_id=channel.server_id,
        executor_id=channel.executor_id,remote_ready=True,channel=channel)
    assert reserved is not None
    sent = begin_execution_send(deps.connection_factory,reservation=reserved,remote_ready=True,
        fresh_publications=owner.fresh,access=access,channel=channel)
    monkeypatch.setenv("LOCAL_TEST_KEY","technical-provider-secret")
    return local_setup, sent, channel, access


def test_approved_local_configuration_reaches_core(admitted_local):
    setup,sent,channel,access=admitted_local
    deps,app,client,_,_,candidate,root=setup
    leases=ExecutionLeaseService(factory=deps.connection_factory,access=access,
                                 fresh_publications=app.state.inventory_fresh_publications)
    class Factory(_NativeFactory):
        opens=0
        async def open(self,prepared,*args,**kwargs):
            self.opens+=1
            assert prepared.secret_refs == ("provider:LOCAL_TEST_KEY",)
            return await super().open(prepared,*args,**kwargs)
    native=Factory()
    async def scenario():
        async def grant(request):
            return leases.issue(request,channel=channel)
        async def forbidden(_):
            raise AssertionError("The caller must not replace approved local configuration")
        executor,application=await EmbeddedExecutor.authorize_r4(app.state.embedded_core_host,
            scope=sent.scope,grant_id=sent.grant_id,connection_id=channel.connection_id,
            connection_generation=channel.connection_generation,request_grant=grant,
            candidate=candidate,workspace_root=str(root.resolve()),environment=forbidden,native_factory=native)
        leases.applied(application.acknowledgement,channel=channel)
        # The technical native factory bypasses actual process creation; exercise
        # the exact Core environment callback separately with its prepared refs.
        prepared=SimpleNamespace(intent=SimpleNamespace(adapter_id=candidate.adapter_id,
            agent_id="subject",workspace_id=sent.scope["workspace_id"]),secret_refs=executor.local_launch.auth_refs)
        environment=await executor.environment(prepared)
        assert environment["OPENAI_API_KEY"] == "technical-provider-secret"
        receipt=await executor.open(operation_id=sent.frame["operation_id"],stream_epoch="local-stream")
        assert receipt.operation_id == sent.frame["operation_id"] and native.opens == 1
        await app.state.embedded_core_host.shutdown(ShutdownPolicy(0,0))
    client.portal.call(scenario)


@pytest.mark.parametrize("change",["record","root","binary","owner","profile"])
def test_local_configuration_drift_is_refused(admitted_local,change):
    setup,sent,_,_=admitted_local
    deps,app,client,_,_,candidate,root=setup
    if change=="root":
        other=root.with_name("old-root")
        assert other.resolve().parent == root.resolve().parent
        root.rename(other)
        root.mkdir()
    elif change=="binary":
        Path(candidate.executable).write_bytes(b"changed")
    else:
        with deps.connection_factory.unit_of_work() as uow:
            if change=="record":
                record=json.loads(uow.connection.execute("SELECT local_record_json FROM execution_local_realizations").fetchone()[0])
                record["configuration"]["secret_bindings"]={}
                uow.connection.execute("UPDATE execution_local_realizations SET local_record_json=?",(json.dumps(record),))
            elif change=="owner":
                uow.connection.execute("UPDATE execution_executors SET generation=generation+1 WHERE kind='embedded'")
            else:
                uow.connection.execute("UPDATE runtime_profiles SET revision=revision+1")
    async def scenario():
        async def forbidden(_):
            raise AssertionError("Rejected local configuration must not request a lease or environment")
        with pytest.raises((CoreError, OktoNexusError)):
            await EmbeddedExecutor.authorize_r4(app.state.embedded_core_host, scope=sent.scope,
                grant_id=sent.grant_id,connection_id=sent.connection_id,
                connection_generation=sent.connection_generation,request_grant=forbidden,
                candidate=candidate,workspace_root=str(root),environment=forbidden)
    client.portal.call(scenario)
    assert not (deps.config.home_dir/"core-runtime").exists()


def test_authority_change_during_secret_resolution_is_refused(admitted_local):
    setup,sent,_,_=admitted_local
    deps,app,client,_,_,candidate,_=setup
    class Resolver:
        async def resolve(self,reference):
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='subject'")
            return "technical-secret"
    launch=ApprovedLocalLaunch(app.state.embedded_inventory_owner,sent.scope,resolver=Resolver())
    prepared=SimpleNamespace(intent=SimpleNamespace(adapter_id=candidate.adapter_id,
        agent_id="subject",workspace_id=sent.scope["workspace_id"]),secret_refs=launch.auth_refs)
    async def scenario():
        with pytest.raises((CoreError, OktoNexusError)):
            await launch.environment(prepared)
    client.portal.call(scenario)
    assert not (deps.config.home_dir/"core-runtime").exists()


@pytest.mark.parametrize("value",[None,"nxc4_not_a_provider_secret"])
def test_missing_or_nexus_credentials_cannot_be_provider_secrets(admitted_local,monkeypatch,value):
    setup,sent,_,_=admitted_local
    deps,app,client,_,_,candidate,_=setup
    if value is None:
        monkeypatch.delenv("LOCAL_TEST_KEY")
    else:
        monkeypatch.setenv("LOCAL_TEST_KEY",value)
    launch=ApprovedLocalLaunch(app.state.embedded_inventory_owner,sent.scope)
    prepared=SimpleNamespace(intent=SimpleNamespace(adapter_id=candidate.adapter_id,
        agent_id="subject",workspace_id=sent.scope["workspace_id"]),secret_refs=launch.auth_refs)
    async def scenario():
        with pytest.raises(CoreError) as error:
            await launch.environment(prepared)
        assert error.value.code == "PROVIDER_AUTH_REQUIRED"
    client.portal.call(scenario)
    assert not (deps.config.home_dir/"core-runtime").exists()
