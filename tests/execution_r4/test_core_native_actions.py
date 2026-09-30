"""Core bridge through embedded/HTTP backends and canonical handoff transactions.

The selected harness is a technical peer. This does not qualify a provider,
automatic daemon composition, native Pi socket ownership or a release build.
"""
import asyncio
from contextlib import AsyncExitStack
from types import SimpleNamespace
import time

import httpx
import pytest

from nexus_connector_core import (
    CoreError, InstallationCandidate, LaunchIntent, OpenOperation, ShutdownPolicy,
    create_runtime, r4_lease_renew_frame,
)
from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.journal import open_journal
from nexus_connector_core.native_action_bridge import (
    ContextGet, HandoffClaim, HandoffComplete, NativeActionGrant,
)
from okto_nexus.adapters.outbound.execution.core_native_actions import embedded_native_action_bridge
from okto_nexus.application.execution_leases import ExecutionLeaseService
from test_native_actions import opening, rows
from test_mcp_session_capabilities import seed_work
from test_session_capabilities import issue, begin
from test_vertical_inventory import _NativeFactory


@pytest.mark.parametrize("backend", ["embedded", "connector"])
@pytest.mark.parametrize("fault", ["none", "lost_response", "server_revocation"])
@pytest.mark.parametrize("opening", ["strict"], indirect=True)
def test_core_native_bridge_uses_same_lease_and_canonical_domain(opening, tmp_path, monkeypatch, backend, fault):
    if backend == "connector":
        from okto_nexus_connector.transport.https_client import NexusHTTPClient, R4SessionCapability
        from okto_nexus_connector.transport.native_actions import native_action_bridge
    deps, app, access, _, _, channel, _, _ = opening
    issued = issue(opening, audience="nexus-native-session",
        actions=["handoff.get", "handoff.claim", "handoff.complete"]).json()
    seed_work(opening)
    sent = begin(opening)
    async def run():
        journal = await open_journal(tmp_path / "bridge.db")
        binary = tmp_path / "codex.exe"
        candidate = InstallationCandidate("codex_app_server", str(binary), fingerprint(binary),
                                          "explicit", "selected")
        async def environment(_): return {}
        runtime = create_runtime(journal=journal, environment=environment, lease_poll_seconds=3600,
            candidates={candidate.adapter_id: candidate}, workspace_roots={"ws": str(tmp_path)},
            native_factory=_NativeFactory())
        try:
            attempt = await runtime.begin_r4_lease_request(scope=sent.scope, grant_id=sent.grant_id,
                connection_id=channel.connection_id, connection_generation=channel.connection_generation,
                purpose="initial")
            leases = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                fresh_publications=app.state.inventory_fresh_publications)
            granted = leases.issue(r4_lease_renew_frame(attempt), channel=channel)
            installed = await runtime.install_r4_lease(attempt, granted)
            leases.applied(installed.acknowledgement, channel=channel)
            context = installed.context
            prepared = await runtime.prepare(LaunchIntent("subject", "ws", "codex_app_server"), context)
            await runtime.open(OpenOperation(sent.frame["operation_id"], sent.scope["session_id"],
                                             "epoch", prepared), context)
            # READY receipt materialization is independently covered by the public open campaign.
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY'")
            cap_type = R4SessionCapability if backend == "connector" else SimpleNamespace
            cap = cap_type(capability_id=issued["capability_id"], capability_ref=issued["capability_ref"],
                capability=issued["capability"], scope=issued["scope"], audience=issued["audience"],
                actions=tuple(issued["actions"]), expires_in=issued["expires_in"],
                deadline_monotonic=time.monotonic() + issued["expires_in"] - .5, mcp_url=None)
            async with AsyncExitStack() as stack:
                if backend == "connector":
                    raw = await stack.enter_async_context(httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False)))
                    http = await stack.enter_async_context(NexusHTTPClient("https://127.0.0.1:8202", client=raw))
                    bridge = native_action_bridge(http, cap, runtime, connection_id=channel.connection_id,
                                                  connection_generation=channel.connection_generation)
                else:
                    s = cap.scope
                    grant = NativeActionGrant(cap.capability_ref, s["server_id"], s["executor_id"],
                        s["binding_id"], s["agent_id"], s["workspace_id"], s["session_id"],
                        channel.connection_generation, s["authorization_revision"], s["configuration_revision"],
                        cap.deadline_monotonic, frozenset(cap.actions), s, channel.connection_id)
                    bridge = embedded_native_action_bridge(deps, grant, cap.capability, runtime)
                assert not (set(cap.actions) & context.allowed_actions)
                base = (cap.scope["session_id"], cap.capability_ref, "work")
                read = await bridge.invoke(ContextGet("read", *base), context)
                assert read["status"] == "OPEN"
                claim = HandoffClaim("claim", *base, "original-key")
                if fault == "server_revocation":
                    with deps.connection_factory.unit_of_work() as uow:
                        uow.connection.execute("UPDATE execution_session_capabilities SET revoked_at=?",
                                               (deps.clock.now_iso(),))
                    with pytest.raises(CoreError) as rejected:
                        await bridge.invoke(claim, context)
                    assert not rejected.value.possible_effect
                    assert rows(opening) == (("OPEN", 0), 1, 0)
                    return
                if fault == "lost_response":
                    from okto_nexus.application.execution_native_actions import NativeActionService
                    original = NativeActionService.invoke
                    def lose(self, **kwargs):
                        original(self, **kwargs)
                        raise RuntimeError("Injected response loss after canonical commit.")
                    with monkeypatch.context() as patch:
                        patch.setattr(NativeActionService, "invoke", lose)
                        with pytest.raises(CoreError) as lost:
                            await bridge.invoke(claim, context)
                        assert lost.value.code == "OUTCOME_UNKNOWN"
                        assert lost.value.possible_effect and not lost.value.retry_safe
                        assert lost.value.operation_id == "claim"
                    assert rows(opening) == (("CLAIMED", 1), 2, 1)
                claimed = await bridge.invoke(claim, context)
                assert await bridge.invoke(claim, context) == claimed
                done = HandoffComplete("complete", *base, claimed["claim_epoch"], {"summary": "Done."})
                assert (await bridge.invoke(done, context))["status"] == "COMPLETED"
                assert (await bridge.invoke(done, context))["status"] == "COMPLETED"
                assert rows(opening) == (("COMPLETED", 1), 3, 1)
                await runtime.revoke_r4_lease(context, authorization_revision=context.authorization_revision + 1)
                with pytest.raises(CoreError):
                    await bridge.invoke(ContextGet("after-revoke", *base), context)
                assert rows(opening) == (("COMPLETED", 1), 3, 1)
        finally:
            await runtime.shutdown(ShutdownPolicy(0, 0))
            journal.close()
    asyncio.run(run())
