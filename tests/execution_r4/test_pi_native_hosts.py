# A technical Pi CLI runs through the real Core copied adapter and owned child.
# Qualification and Server READY are explicit fixtures, not provider acceptance.
import asyncio
from contextlib import AsyncExitStack
import json
from pathlib import Path
import shutil
import threading
import time

from fastapi.testclient import TestClient
import httpx
import pytest

from nexus_connector_core import (
    CloseOperation, LaunchIntent, OpenOperation, SessionKey, ShutdownPolicy, TurnOperation,
    calculate_inventory_revision, r4_lease_renew_frame,
)
from nexus_connector_core.discovery import candidate_pi_node_cli
from nexus_connector_core.environment import child_environment
from nexus_connector_core.native_action_bridge import NativeActionGrant
from okto_nexus.adapters.outbound.execution.core_native_actions import embedded_native_action_owner_factory
from okto_nexus.adapters.outbound.execution.embedded import EmbeddedExecutor
from okto_nexus.application.execution_dispatch import begin_execution_send, reserve_execution_dispatch
from okto_nexus.application.execution_leases import ExecutionLeaseService
from okto_nexus.bootstrap.runtime_host import EmbeddedRuntimeHost
from test_ns09 import setup_authority, negotiate, admit
from test_mcp_session_capabilities import seed_work

PEER = r'''
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";
import { writeFileSync } from "node:fs";
if (process.argv.includes("--version")) {
  console.log("0.87.1");
  process.exit(0);
}
const extensionPath = process.argv[process.argv.indexOf("--extension") + 1];
const { default: extension } = await import(pathToFileURL(extensionPath).href);
const tools = new Map();
extension({registerTool(tool) { tools.set(tool.name, tool); }});
const emit = (value) => process.stdout.write(JSON.stringify(value) + "\n");
const peer = createInterface({input: process.stdin});
peer.on("line", async (line) => {
  const command = JSON.parse(line);
  emit({type:"response", id:command.id, command:command.type, success:true, data:{}});
  if (command.type === "prompt") {
    emit({type:"agent_start"});
    try {
      const read = await tools.get("nexus_handoff_get").execute("pi-read", {handoff_id:"work"});
      const claim = await tools.get("nexus_handoff_claim").execute("pi-claim",
          {handoff_id:"work", idempotency_key:"pi-key"});
      const replay = await tools.get("nexus_handoff_claim").execute("pi-claim",
          {handoff_id:"work", idempotency_key:"pi-key"});
      const complete = await tools.get("nexus_handoff_complete").execute("pi-complete",
          {handoff_id:"work", claim_epoch:claim.details.claim_epoch, result:{summary:"Done from Pi."}});
      writeFileSync(process.env.PI_TEST_RESULT, JSON.stringify({
        ok:true, read:read.details.status, epoch:claim.details.claim_epoch,
        replay:replay.details.claim_epoch, complete:complete.details.status,
        port:Number(process.env.NEXUS_NATIVE_ACTION_PORT),
        raw_capability_present:Object.values(process.env).some((v) => v.startsWith("nxc4_")),
        native_ref_in_argv:process.argv.some((v) => v.startsWith("native-cap:")),
        extension:extensionPath
      }));
    } catch (error) {
      writeFileSync(process.env.PI_TEST_RESULT, JSON.stringify({ok:false,error:String(error)}));
    }
    emit({type:"agent_settled"});
  }
});
peer.on("close", () => process.exit(0));
'''


def technical_pi(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("The technical Pi child requires Node.")
    package = tmp_path / "node_modules" / "@earendil-works" / "pi-coding-agent"
    entry = package / "dist" / "bundle" / "cli.js"
    entry.parent.mkdir(parents=True)
    entry.write_text(PEER, encoding="utf-8")
    (package / "package.json").write_text(json.dumps({
        "name":"@earendil-works/pi-coding-agent", "version":"0.87.1", "type":"module"}))
    return candidate_pi_node_cli(Path(node), entry, explicit=True)


@pytest.mark.parametrize("backend", ["embedded", "connector"])
@pytest.mark.parametrize("held", [False, True])
def test_owned_pi_child_reaches_canonical_domain_and_retains_pending_shutdown(tmp_path, monkeypatch, backend, held):
    import nexus_connector_core.native.runtime_bridge as bridge_module
    candidate = technical_pi(tmp_path)
    # Only this technical peer is used; this does not qualify a real Pi build.
    monkeypatch.setattr(bridge_module, "qualified_build", lambda *a, **kw: True)
    values = setup_authority(tmp_path, monkeypatch, candidate=candidate)
    deps, app, access, _, canonical, candidate, info, revisions, link, lane, server_id, executor_id = values
    entered, release = threading.Event(), threading.Event()
    if held:
        from okto_nexus.application.execution_native_actions import NativeActionService
        original = NativeActionService.invoke
        def retain(self, **kwargs):
            result = original(self, **kwargs)
            if kwargs["body"]["action"] == "claim":
                entered.set()
                assert release.wait(30), "The test did not release the committed claim."
            return result
        monkeypatch.setattr(NativeActionService, "invoke", retain)
    result_file = tmp_path / "pi-result.json"
    class NoSecrets:
        async def resolve(self, reference):
            raise AssertionError("Native capabilities must stay in the trusted host.")
    async def environment(prepared):
        return await child_environment(prepared, NoSecrets(),
                                       public_overrides={"PI_TEST_RESULT":str(result_file)})
    with TestClient(app, base_url="https://127.0.0.1:8202") as client:
        with client.websocket_connect(f"wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link",
                headers={"Authorization":"Bearer " + link}, subprotocols=["nxl.v1"]) as ws:
            channel = negotiate(ws, info, revisions, lane, server_id, executor_id)
            resolution = admit(deps, app)
            scope = resolution["scope"]
            if backend == "embedded":
                response = client.post(f"/v1/runtime/sessions/{scope['session_id']}/capability",
                    headers={"Authorization":"Bearer " + app.state.test_agent_keys["subject"]},
                    json=dict(capability_request_id="native", binding_id="binding",
                              audience="nexus-native-session", actions=["handoff.get","handoff.claim","handoff.complete"]))
                assert response.status_code == 200, response.text
                cap = response.json()
            state = (deps, app)
            seed_work(state)
            reserved = reserve_execution_dispatch(deps.connection_factory, server_id=server_id,
                                                   executor_id=executor_id, remote_ready=True)
            sent = begin_execution_send(deps.connection_factory, reservation=reserved,
                remote_ready=True, fresh_publications=app.state.inventory_fresh_publications, access=access)
            leases = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                fresh_publications=app.state.inventory_fresh_publications)
            async def run():
                async with AsyncExitStack() as stack:
                    if backend == "embedded":
                        grant = NativeActionGrant(cap["capability_ref"], server_id, executor_id, "binding", "subject",
                            "ws", scope["session_id"], channel.connection_generation, scope["authorization_revision"],
                            scope["configuration_revision"], time.monotonic() + cap["expires_in"] - .5,
                            frozenset(cap["actions"]), scope, channel.connection_id)
                        launch = embedded_native_action_owner_factory(deps, grant, cap["capability"])
                        host = EmbeddedRuntimeHost(tmp_path / "embedded-core")
                        async def issue(request):
                            return leases.issue(request, channel=channel)
                        executor, applied = await EmbeddedExecutor.authorize_r4(host, scope=scope,
                            grant_id=sent.grant_id, connection_id=channel.connection_id,
                            connection_generation=channel.connection_generation, candidate=candidate,
                            workspace_root=str(tmp_path), environment=environment, request_grant=issue,
                            native_action_factory=launch)
                        runtime = await executor._runtime()
                        _, journal = await host._runtime_tasks[(executor_id, scope["session_id"])]
                        async def shutdown():
                            return await host.shutdown(ShutdownPolicy(.2, .2))
                    else:
                        from okto_nexus_connector.services.core_host import CoreRuntimeHost, ExecutionRuntimeKey
                        from okto_nexus_connector.services.execution_selection import acknowledge_execution_binding
                        from okto_nexus_connector.services.realization_service import stage_local_realization, acknowledge_local_realization
                        from okto_nexus_connector.storage.state_store import StateStore
                        from okto_nexus_connector.platform.paths import state_dir
                        from okto_nexus_connector.transport.https_client import NexusHTTPClient, R4SessionCapability, R4Realization, R4BindingView
                        from okto_nexus_connector.services.launch_configuration import stage_launch_configuration
                        from okto_nexus_connector.services.session_capabilities import SessionCapabilityOwner, ApprovedNativeLaunchProvider
                        from okto_nexus_connector.identity.vault import RestrictedFileVault
                        store = StateStore(tmp_path / "connector-state.json")
                        revision = calculate_inventory_revision([candidate])
                        vault = RestrictedFileVault(tmp_path, approved=True)
                        result_ref = vault.store("test-result", str(result_file))
                        config = stage_launch_configuration(store, server_id=server_id, executor_id=executor_id,
                            agent_id="subject", local_consent_id="consent", adapter_id="pi_rpc", profile_revision=1,
                            secret_bindings={"PI_TEST_RESULT": result_ref})
                        digest = config.configuration_digest
                        local = stage_local_realization(store, server_id=server_id, executor_id=executor_id,
                            agent_id="subject", client_intent_id="pi-local", candidates=[candidate],
                            adapter_id="pi_rpc", candidate_ref=candidate.installation_ref, inventory_revision=revision,
                            workspace_root=tmp_path, workspace_id="ws", workspace_label="Pi workspace",
                            configuration_digest=digest, local_consent_id="consent")
                        acknowledge_local_realization(store, record=local, published=R4Realization(server_id,
                            executor_id, "real", local.local_realization_ref, 1, "subject", "ws", "wxb", revision, digest))
                        acknowledge_execution_binding(store, binding=R4BindingView("binding", server_id, executor_id,
                            "subject", "ep", "ws", "wxb", "pi_rpc", candidate.installation_ref, revision,
                            "real", 1, 1, scope["authorization_revision"], scope["configuration_revision"], "APPROVED"))
                        raw = await stack.enter_async_context(httpx.AsyncClient(transport=httpx.ASGITransport(app=app)))
                        http = await stack.enter_async_context(NexusHTTPClient("https://127.0.0.1:8202", client=raw))
                        host = CoreRuntimeHost(state_dir(tmp_path / "connector-core"), vault)
                        capability_owner = SessionCapabilityOwner(store, vault)
                        stack.push_async_callback(capability_owner.close)
                        async def candidates(frame):
                            return [candidate]
                        provider = ApprovedNativeLaunchProvider(capability_owner, http,
                            app.state.test_agent_keys["subject"], host, store,
                            candidate_provider=candidates, require_current=lambda frame: None)
                        setup = await provider(sent.frame)
                        assert store.load().session_capabilities[0].status == "STORED"
                        runtime = await host.build_r4(store, frame=sent.frame, candidates=[candidate],
                            environment=setup.environment, native_action_factory=setup.native_action_factory)
                        journal = await host.ensure_journal()
                        attempt = await runtime.begin_r4_lease_request(scope=scope, grant_id=sent.grant_id,
                            connection_id=channel.connection_id, connection_generation=channel.connection_generation,
                            purpose="initial")
                        applied = await runtime.install_r4_lease(attempt, leases.issue(r4_lease_renew_frame(attempt), channel=channel))
                        async def shutdown():
                            return await host.shutdown_all()
                    closes = []
                    original_close = journal.aclose
                    async def close_journal():
                        closes.append(True)
                        await original_close()
                    monkeypatch.setattr(journal, "aclose", close_journal)
                    leases.applied(applied.acknowledgement, channel=channel)
                    try:
                        if backend == "embedded":
                            await executor.open(operation_id=sent.frame["operation_id"], stream_epoch="epoch",
                                                auth_refs=(cap["capability_ref"],))
                        else:
                            prepared = await runtime.prepare(LaunchIntent("subject","ws","pi_rpc",
                                auth_refs=setup.auth_refs), applied.context)
                            await runtime.open(OpenOperation(sent.frame["operation_id"], scope["session_id"], "epoch",
                                                             prepared), applied.context)
                        with deps.connection_factory.unit_of_work() as uow:
                            uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY'")
                        await runtime.submit(TurnOperation("turn", scope["session_id"], "Run the native work."), applied.context)
                        if held:
                            assert await asyncio.to_thread(entered.wait, 10)
                            report = await shutdown()
                            if backend == "embedded":
                                assert report[(executor_id, scope["session_id"])].session_outcomes[
                                    SessionKey(server_id, executor_id, scope["session_id"])] == "unknown"
                            else:
                                assert (scope["session_id"], "unknown") in report
                            assert not closes, "The host closed storage with a pending domain producer."
                            release.set()
                            if backend == "embedded":
                                assert await host.close_native_actions(executor_id=executor_id,
                                    session_id=scope["session_id"], timeout_seconds=5)
                            else:
                                assert await host.close_native_actions(ExecutionRuntimeKey(server_id, executor_id,
                                    "binding", scope["session_id"]), timeout_seconds=5)
                            await shutdown()
                            assert closes
                        else:
                            async with asyncio.timeout(10):
                                while not result_file.exists():
                                    await asyncio.sleep(.02)
                            result = json.loads(result_file.read_text())
                            assert result["ok"], result
                            assert (result["read"],result["epoch"],result["replay"],result["complete"]) == ("OPEN",1,1,"COMPLETED")
                            assert not result["raw_capability_present"] and not result["native_ref_in_argv"]
                            assert "nexus_connector_core" in result["extension"]
                            if backend == "embedded":
                                committed, allow_commit = asyncio.Event(), asyncio.Event()
                                record = runtime._journal.record_receipt
                                async def delayed_record(key, receipt):
                                    if key.operation_id == "close" and receipt.stage == "SUCCEEDED":
                                        committed.set()
                                        await allow_commit.wait()
                                    return await record(key, receipt)
                                monkeypatch.setattr(runtime._journal, "record_receipt", delayed_record)
                                closing = asyncio.create_task(executor.close(
                                    operation_id="close", policy=ShutdownPolicy(1,1)))
                                try:
                                    await asyncio.wait_for(committed.wait(), 5)
                                    await asyncio.sleep(2.1)
                                    assert not closing.done()
                                    allow_commit.set()
                                    assert (await asyncio.wait_for(closing, 5)).stage == "SUCCEEDED"
                                finally:
                                    allow_commit.set()
                                    await asyncio.gather(closing, return_exceptions=True)
                            else:
                                await runtime.close(CloseOperation("close", scope["session_id"], "Done.",
                                                                 ShutdownPolicy(1,1)), applied.context)
                                await host.close_native_actions(ExecutionRuntimeKey(server_id, executor_id, "binding", scope["session_id"]))
                            with pytest.raises((ConnectionError, OSError)):
                                await asyncio.open_connection("127.0.0.1", result["port"])
                        with deps.connection_factory.unit_of_work(write=False) as uow:
                            row = tuple(uow.connection.execute("SELECT status,claim_epoch FROM handoffs WHERE handoff_id='work'").fetchone())
                            assert row == (("CLAIMED" if held else "COMPLETED"), 1)
                            assert uow.connection.execute("SELECT count(*) FROM events WHERE type='handoff.claimed'").fetchone()[0] == 1
                    finally:
                        release.set()
                        await shutdown()
            asyncio.run(run())
