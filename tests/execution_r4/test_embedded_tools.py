"""Automatic local capability/configuration reaches real HTTP MCP handlers."""
import asyncio
import json
from pathlib import Path
import time
import tomllib

import pytest

from test_embedded_dispatch import qualified_contract, connected_local, admit, wait_receipt
from test_embedded_dispatch import connect_local
from test_local_realization import local_setup
from test_mcp_session_capabilities import rpc,envelope,seed_work,args


class Vault:
    def __init__(self): self.values={}
    def store(self,key,value): self.values[key]=value
    def remove(self,key): del self.values[key]


def enable_tools(connected_local):
    setup,binding,native=connected_local
    deps,app,client,*_=setup
    deps.runtime_owner_api_url="http://127.0.0.1:8202"
    vault=Vault()
    owner=app.state.embedded_dispatch_owner
    owner.tools.vault=vault
    environments=[]
    original=native.open
    async def capture(prepared,session_id,context,**kwargs):
        environment=await owner.sessions[session_id]["executor"].environment(prepared)
        environments.append(environment)
        return await original(prepared,session_id,context,**kwargs)
    native.open=capture
    return setup,binding,native,vault,environments


def test_automatic_mcp_configuration_claims_work_and_cleans_secret(connected_local,monkeypatch):
    setup,binding,native,vault,environments=enable_tools(connected_local)
    deps,app,client,headers,*_=setup
    monkeypatch.setattr(app.state.embedded_dispatch_owner.leases,"max_duration_ms",2000)
    opened=admit(setup,binding,"tools-open","runtime.start",new_session=True)
    wait_receipt(setup,opened)
    assert len(vault.values)==1 and native.opens==1
    config_path=Path(environments[0]["HOME"])/".codex/config.toml"
    entry=tomllib.loads(config_path.read_text())["mcp_servers"]["nexus"]
    secret=environments[0][entry["bearer_token_env_var"]]
    assert secret in vault.values.values() and secret not in config_path.read_text()
    assert entry["url"]=="http://127.0.0.1:8202/mcp"
    who=envelope(rpc(setup,secret))
    assert who["ok"] and who["data"]["session_scope"]==opened["scope"]
    workspace=opened["scope"]["workspace_id"]
    seed_work(setup,workspace=workspace)
    parameters=args(project_root=workspace)
    claim=envelope(rpc(setup,secret,"handoff_claim",parameters))
    assert claim["ok"],claim
    done=envelope(rpc(setup,secret,"handoff_complete",parameters|dict(claim_epoch=claim["data"]["claim_epoch"],result="Reviewed.")))
    assert done["ok"],done
    until=time.monotonic()+5
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            serial=uow.connection.execute("SELECT MAX(lease_serial) FROM execution_leases WHERE status='ACTIVE'").fetchone()[0]
        if serial>=2:
            break
        assert time.monotonic()<until
        time.sleep(.02)
    assert envelope(rpc(setup,secret))["ok"] and len(vault.values)==1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row=uow.connection.execute("SELECT status,metadata_json FROM execution_local_tool_credentials").fetchone()
        assert row["status"]=="STORED" and secret not in row["metadata_json"]
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_link_tickets").fetchone()[0]==0
    closed=admit(setup,binding,"tools-close","runtime.close",session_id=opened["scope"]["session_id"])
    wait_receipt(setup,closed,stages=("SUCCEEDED",))
    assert rpc(setup,secret).status_code in (401,403)
    until=time.monotonic()+5
    while vault.values:
        assert time.monotonic()<until
        time.sleep(.02)
    client.portal.call(app.state.embedded_dispatch_owner.close)
    assert not vault.values


def test_vault_failure_prevents_native_tool_launch(connected_local):
    setup,binding,native,vault,environments=enable_tools(connected_local)
    _,app,*_=setup
    def broken(*args): raise OSError("Technical vault write failure")
    vault.store=broken
    admit(setup,binding,"tools-vault-failure","runtime.start",new_session=True)
    until=time.monotonic()+5
    while 'subject' not in app.state.embedded_dispatch_owner.agents.errors:
        assert time.monotonic()<until
        time.sleep(.02)
    assert isinstance(app.state.embedded_dispatch_owner.agents.errors['subject'],OSError)
    assert app.state.embedded_dispatch_owner.failure is None
    assert native.opens==0 and not environments


def test_cancelled_tool_waiter_keeps_issuance_owned(connected_local,monkeypatch):
    import threading
    setup,binding,native,vault,environments=enable_tools(connected_local)
    _,app,client,*_=setup
    entered,release=threading.Event(),threading.Event()
    original=vault.store
    def held(*args):
        entered.set()
        assert release.wait(10)
        original(*args)
    vault.store=held
    opened=admit(setup,binding,"tools-retained","runtime.start",new_session=True)
    assert entered.wait(5)
    owner=app.state.embedded_dispatch_owner
    async def cancel_observer():
        worker=next(iter(owner.workers))
        worker.cancel()
        await asyncio.gather(worker,return_exceptions=True)
        assert any(not task.done() for _,task in owner.tools.tasks.values())
    try:
        client.portal.call(cancel_observer)
    finally:
        release.set()
    client.portal.call(owner.close)
    assert native.opens==0 and not vault.values


@pytest.mark.parametrize('local_setup', ['pi_rpc'], indirect=True)
def test_automatic_pi_bridge_survives_initial_deadline_with_applied_renewal(connected_local,monkeypatch):
    from okto_nexus.application.execution_capabilities import ExecutionCapabilityService
    from nexus_connector_core.native_action_bridge import ContextGet, HandoffClaim, HandoffComplete
    setup,binding,native,vault,environments=enable_tools(connected_local)
    deps,app,client,*_=setup
    owner=app.state.embedded_dispatch_owner
    monkeypatch.setattr(owner.leases,'max_duration_ms',6000)
    original=ExecutionCapabilityService.issue
    def short_metadata(self,**kwargs):
        return dict(original(self,**kwargs),expires_in=2)
    monkeypatch.setattr(ExecutionCapabilityService,'issue',short_metadata)
    opened=admit(setup,binding,'pi-tools-open','runtime.start',new_session=True)
    wait_receipt(setup,opened)
    session_id=opened['scope']['session_id']
    config=owner.tools.configurations[session_id]
    assert config['native_factory'] is not None, (setup[5].adapter_id,config['cap']['audience'])
    seed_work(setup,workspace=opened['scope']['workspace_id'])
    until=time.monotonic()+10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            serial=uow.connection.execute("SELECT MAX(lease_serial) FROM execution_leases WHERE status='ACTIVE'").fetchone()[0]
        if serial>=2 and time.monotonic()>config['deadline']:
            break
        assert time.monotonic()<until
        time.sleep(.02)
    async def actions():
        host=owner.host
        assert owner.failure is None, repr(owner.failure)
        native_owner=host._native_action_owners[(opened['scope']['executor_id'],session_id)]
        service=native_owner._service
        context=service._context_provider()
        base=(session_id,config['cap']['capability_ref'],'work')
        assert (await service._bridge.invoke(ContextGet('pi-read',*base),context))['status']=='OPEN'
        claimed=await service._bridge.invoke(HandoffClaim('pi-claim',*base,'pi-key'),context)
        assert (await service._bridge.invoke(HandoffComplete('pi-complete',*base,claimed['claim_epoch'],
            {'summary':'Reviewed.'}),context))['status']=='COMPLETED'
    client.portal.call(actions)
    assert native.opens==1 and len(vault.values)==1
    assert config['cap']['capability'] not in json.dumps(environments)
    closed=admit(setup,binding,'pi-tools-close','runtime.close',session_id=session_id)
    wait_receipt(setup,closed,stages=('SUCCEEDED',))
    client.portal.call(owner.close)
    assert not vault.values


@pytest.mark.parametrize('local_setup',['codex_app_server','claude_stream'],indirect=True)
def test_approved_provider_home_uses_process_mcp_without_copying_login(local_setup,tmp_path):
    from nexus_connector_core.environment import ProcessHTTPEnvironment
    provider_home=tmp_path/'approved-home'
    provider_home.mkdir()
    local_setup[4]['provider_home']=str(provider_home)
    setup,binding,native,vault,environments=enable_tools(connect_local(local_setup))
    _,app,client,*_=setup
    opened=admit(setup,binding,'home-tools-open','runtime.start',new_session=True)
    wait_receipt(setup,opened)
    environment=environments[0]
    assert isinstance(environment,ProcessHTTPEnvironment)
    assert environment['HOME']==str(provider_home.resolve())
    def assert_no_configuration_written():
        expected = ['.codex'] if local_setup[5].adapter_id == 'codex_app_server' else []
        assert sorted(p.name for p in provider_home.iterdir()) == expected
        if expected:
            assert environment['CODEX_HOME'] == str((provider_home / '.codex').resolve())
            assert not list((provider_home / '.codex').iterdir())
    assert_no_configuration_written()
    template=environment.http_templates[0]
    assert template.entry_name.startswith('nexus_') and template.entry_name!='nexus'
    assert environment[template.bearer_env_name] in vault.values.values()
    assert envelope(rpc(setup,environment[template.bearer_env_name]))['ok']
    closed=admit(setup,binding,'home-tools-close','runtime.close',session_id=opened['scope']['session_id'])
    wait_receipt(setup,closed,stages=('SUCCEEDED',))
    client.portal.call(app.state.embedded_dispatch_owner.close)
    assert not vault.values
    assert_no_configuration_written()
