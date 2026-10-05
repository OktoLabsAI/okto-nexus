"""Approved MCP environment reaches canonical Nexus tools; technical native peer."""
import asyncio
from pathlib import Path
import tomllib

import httpx
import pytest

from nexus_connector_core import InstallationCandidate, LaunchIntent, OpenOperation, r4_lease_renew_frame
from nexus_connector_core.discovery import fingerprint

from okto_nexus.application.execution_leases import ExecutionLeaseService
from test_session_capabilities import opening, begin
from test_mcp_session_capabilities import seed_work, rpc, envelope, args
from test_vertical_inventory import _NativeFactory


@pytest.mark.parametrize("opening", ["strict"], indirect=True)
def test_approved_mcp_environment_claims_and_completes_with_session_authority(opening, tmp_path):
    from okto_nexus_connector.identity.vault import RestrictedFileVault
    from okto_nexus_connector.storage.state_store import StateStore
    from okto_nexus_connector.services.core_host import CoreRuntimeHost
    from okto_nexus_connector.services.launch_configuration import stage_launch_configuration
    from okto_nexus_connector.services.execution_selection import acknowledge_execution_binding
    from okto_nexus_connector.services.realization_service import stage_local_realization, acknowledge_local_realization
    from okto_nexus_connector.services.session_capabilities import SessionCapabilityOwner, ApprovedToolLaunchProvider
    from okto_nexus_connector.transport.https_client import NexusHTTPClient, R4Realization, R4BindingView

    deps, app, access, _, _, channel, _, _ = opening
    sent = begin(opening)
    frame, scope = sent.frame, sent.scope
    payload = frame["payload"]
    binary = tmp_path / "codex.exe"
    candidate = InstallationCandidate("codex_app_server", str(binary), fingerprint(binary),
        "explicit", "selected", installation_ref=payload["candidate_ref"])
    store = StateStore(tmp_path / "approved-mcp-state.json")
    vault = RestrictedFileVault(tmp_path, approved=True)
    provider_ref = vault.store("provider", "provider-test-secret")
    config = stage_launch_configuration(store, server_id=scope["server_id"],
        executor_id=scope["executor_id"], agent_id="subject", local_consent_id="consent",
        adapter_id=candidate.adapter_id, profile_revision=payload["profile_revision"],
        secret_bindings={"OPENAI_API_KEY": provider_ref})
    local = stage_local_realization(store, server_id=scope["server_id"], executor_id=scope["executor_id"],
        agent_id="subject", client_intent_id="local", candidates=[candidate], adapter_id=candidate.adapter_id,
        candidate_ref=payload["candidate_ref"], inventory_revision=payload["inventory_revision"],
        workspace_root=tmp_path, workspace_id="ws", workspace_label="Workspace",
        configuration_digest=config.configuration_digest, local_consent_id="consent")
    acknowledge_local_realization(store, record=local, published=R4Realization(scope["server_id"],
        scope["executor_id"], payload["realization_ref"], local.local_realization_ref,
        payload["realization_revision"], "subject", "ws", "wxb", payload["inventory_revision"],
        config.configuration_digest))
    acknowledge_execution_binding(store, binding=R4BindingView("binding", scope["server_id"],
        scope["executor_id"], "subject", "ep", "ws", "wxb", candidate.adapter_id,
        payload["candidate_ref"], payload["inventory_revision"], payload["realization_ref"],
        payload["realization_revision"], scope["binding_revision"], scope["authorization_revision"],
        scope["configuration_revision"], "APPROVED"))
    seed_work(opening)

    async def run():
        host = CoreRuntimeHost(tmp_path / "mcp-host", vault)
        cap_owner = SessionCapabilityOwner(store, vault)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as raw:
                async with NexusHTTPClient("https://127.0.0.1:8202", client=raw) as http:
                    async def candidates(_):
                        return [candidate]
                    provider = ApprovedToolLaunchProvider(cap_owner, http, app.state.test_agent_keys["subject"],
                        host, store, candidate_provider=candidates, require_current=lambda frame: None)
                    setup = await provider(frame)
                    runtime = await host.build_r4(store, frame=frame, candidates=[candidate],
                        environment=setup.environment, factory=_NativeFactory())
                    attempt = await runtime.begin_r4_lease_request(scope=scope, grant_id=sent.grant_id,
                        connection_id=channel.connection_id, connection_generation=channel.connection_generation,
                        purpose="initial")
                    leases = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                        fresh_publications=app.state.inventory_fresh_publications)
                    installed = await runtime.install_r4_lease(attempt,
                        leases.issue(r4_lease_renew_frame(attempt), channel=channel))
                    leases.applied(installed.acknowledgement, channel=channel)
                    prepared = await runtime.prepare(LaunchIntent("subject", "ws", candidate.adapter_id,
                        auth_refs=setup.auth_refs), installed.context)
                    env = await setup.environment(prepared)
                    path = Path(env["HOME"]) / ".codex/config.toml"
                    entry = tomllib.loads(path.read_text())["mcp_servers"]["nexus"]
                    secret = env[entry["bearer_token_env_var"]]
                    assert entry["url"] == "https://127.0.0.1:8202/mcp"
                    assert secret not in path.read_text() and secret not in store.path.read_text()
                    assert env["OPENAI_API_KEY"] == "provider-test-secret"
                    await runtime.open(OpenOperation(frame["operation_id"], scope["session_id"], "epoch", prepared),
                                       installed.context)
                    with deps.connection_factory.unit_of_work() as uow:
                        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY'")
                    who = envelope(await asyncio.to_thread(rpc, opening, secret))
                    assert who["ok"] and who["data"]["session_scope"] == scope
                    claim = envelope(await asyncio.to_thread(rpc, opening, secret, "handoff_claim", args()))
                    assert claim["ok"], claim
                    done = envelope(await asyncio.to_thread(rpc, opening, secret, "handoff_complete",
                        args(claim_epoch=claim["data"]["claim_epoch"], result="Reviewed.")))
                    assert done["ok"], done
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id='work'").fetchone()[0] == "COMPLETED"
                        assert uow.connection.execute("SELECT COUNT(*) FROM execution_session_capabilities").fetchone()[0] == 1
        finally:
            await cap_owner.close()
            await host.shutdown_all()
    asyncio.run(run())
