"""Boot consent and bounded admission remain independent of native startup."""
import asyncio
from types import SimpleNamespace

import pytest
from nexus_connector_core import CoreError
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, connect_local, wait_receipt
from test_canonical_boot import configure
from test_agent_recovery_isolation import create_agent, eventually
from test_vertical_inventory import _Native
from okto_nexus.adapters.inbound.mcp.tools import harness


@pytest.mark.parametrize("fault", ["failed", "hung"])
def test_one_native_boot_does_not_block_another_agent(connected_local, fault):
    setup, first, _ = connected_local
    deps, app, client, *_ = setup
    second_setup = create_agent(setup, "healthy")
    _, second, _ = connect_local(second_setup, agent_id="healthy")
    for binding in (first, second):
        configure(setup, binding)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET priority=100 WHERE endpoint_id=?", (first["endpoint_id"],))
    release = asyncio.Event()
    starts = []
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            starts.append(context.agent_id)
            if context.agent_id == "subject":
                if fault == "failed":
                    raise CoreError("NATIVE_START_FAILED", "fixture", retry_safe=True)
                await release.wait()
            return _Native()
    owner = app.state.embedded_dispatch_owner
    owner.native_factory = Factory()
    try:
        boots = harness.run_runtime_boot(deps)
        assert [b["endpoint_id"] for b in boots] == [first["endpoint_id"], second["endpoint_id"]]
        assert all(b["state"] == "ACCEPTED" for b in boots), boots
        healthy = next(b for b in boots if b["endpoint_id"] == second["endpoint_id"])
        wait_receipt(second_setup, healthy)
        eventually(lambda: "subject" in starts)
        assert starts.count("healthy") == starts.count("subject") == 1
        assert owner.failure is None and owner.pump.error is None
        if fault == "hung":
            assert not release.is_set()
        repeated = harness.run_runtime_boot(deps)
        assert [b["operation_id"] for b in repeated] == [b["operation_id"] for b in boots]
        assert all(b["reused"] for b in repeated)
        assert len(starts) == 2
    finally:
        client.portal.call(release.set)


@pytest.mark.parametrize("change", ["disabled", "profile_revision", "issuer_rotated", "quarantined"])
def test_boot_revalidates_persisted_consent_before_admission(connected_local, change):
    setup, binding, native = connected_local
    deps = setup[0]
    configure(setup, binding)
    with deps.connection_factory.unit_of_work() as uow:
        if change == "disabled":
            uow.connection.execute("UPDATE runtime_boot_bindings SET enabled=0")
        elif change == "profile_revision":
            uow.connection.execute("UPDATE runtime_profiles SET revision=revision+1")
        elif change == "issuer_rotated":
            uow.connection.execute("UPDATE agents SET api_key_hash='rotated-operator' WHERE agent_id='operator'")
        else:
            uow.connection.execute("UPDATE agent_endpoints SET health='quarantined'")
    boots = harness.run_runtime_boot(deps)
    if change == "disabled":
        assert boots == []
    else:
        assert len(boots) == 1 and boots[0]["state"] == "blocked", boots
    assert native.opens == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0


def test_boot_authority_is_bound_to_one_endpoint_and_open_only(connected_local):
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    from okto_nexus.errors import OktoNexusError
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    response = client.put(f"/api/v1/harness/endpoints/{binding['endpoint_id']}/boot",
        headers=headers["subject"], json=dict(enabled=True, expected_revision=1))
    assert response.status_code == 403, response.text
    configure(setup, binding)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        workspace = uow.connection.execute("SELECT workspace_id FROM agent_endpoints WHERE endpoint_id=?",
            (binding["endpoint_id"],)).fetchone()[0]
    context = RuntimeRequestContext(None, "runtime_boot", represented_agent_id="subject",
        endpoint_id=binding["endpoint_id"], workspace_id=workspace,
        runtime_owner_id=deps.runtime_dispatcher.owner_id, runtime_owner_epoch=deps.runtime_dispatcher.epoch)
    access = build_execution_access(deps)
    access.authorize(context, action="open", endpoint_id=binding["endpoint_id"])
    for action, endpoint in (("send", binding["endpoint_id"]), ("admin", binding["endpoint_id"]), ("open", "other-endpoint")):
        with pytest.raises(OktoNexusError, match="PERMISSION_DENIED"):
            access.authorize(context, action=action, endpoint_id=endpoint)
    assert native.opens == 0


@pytest.mark.parametrize("budget", [0, .1, 60])
def test_boot_budget_bounds_admission_without_waiting_for_native(connected_local, monkeypatch, budget):
    from okto_nexus.application import runtime_boot
    from okto_nexus.bootstrap.execution_compat import boot_endpoint
    from okto_nexus.adapters.outbound.sqlite.endpoints_repo import SqliteEndpointRepo
    setup, first, native = connected_local
    deps, app, client, *_ = setup
    second_setup = create_agent(setup, "second")
    _, second, native = connect_local(second_setup, agent_id="second")
    for binding in (first, second):
        configure(setup, binding)
    clock, calls = SimpleNamespace(now=0.0), []
    monkeypatch.setattr(runtime_boot, "time", SimpleNamespace(monotonic=lambda: clock.now))
    def bounded(context, endpoint, key):
        calls.append(endpoint)
        result = boot_endpoint(deps, context, endpoint, key)
        clock.now += min(budget, 30)
        return result
    service = runtime_boot.RuntimeBootService(connection_factory=deps.connection_factory,
        endpoints=SqliteEndpointRepo(), registry=None, open_service=None,
        owner_id=deps.runtime_dispatcher.owner_id, owner_epoch=deps.runtime_dispatcher.epoch,
        canonical_open=bounded)
    lock = app.state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        boots = service.run(budget_seconds=budget)
        assert len(boots) == 2
        assert len(calls) == (0 if budget == 0 else 1)
        if budget:
            assert boots[0]["state"] == "ACCEPTED"
        assert boots[-1]["state"] == "deferred" and boots[-1]["reason"] == "startup_budget"
        assert native.opens == 0
    finally:
        client.portal.call(lock.release)


def test_attach_pid_cannot_authorize_automatic_boot(connected_local):
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET adapter_id='claude_attach' WHERE endpoint_id=?", (binding["endpoint_id"],))
        revision = uow.connection.execute("SELECT revision FROM agent_endpoints WHERE endpoint_id=?", (binding["endpoint_id"],)).fetchone()[0]
    response = client.put(f"/api/v1/harness/endpoints/{binding['endpoint_id']}/boot", headers=headers["operator"],
        json=dict(enabled=True, expected_revision=revision))
    assert response.status_code == 422, response.text
    assert "PID alone" in response.text
    assert harness.run_runtime_boot(deps) == [] and native.opens == 0


def test_uncertain_boot_is_not_replayed_after_server_restart(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from fastapi.testclient import TestClient
    from nexus_connector_core import LocalRuntimeCore
    from test_embedded_inventory import app_for
    calls = []
    async def uncertain(*args, **kwargs):
        # Inject at the Core boundary: an actual unknown process would retain
        # ownership until contained and cannot be released by a test fixture.
        calls.append(1)
        raise CoreError("OUTCOME_UNKNOWN", "fixture", possible_effect=True)
    with monkeypatch.context() as patch:
        patch.setattr(LocalRuntimeCore, "open", uncertain)
        with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as setup:
            setup, binding, native = connect_local(setup)
            configure(setup, binding)
            original = harness.run_runtime_boot(setup[0])[0]
            owner = setup[1].state.embedded_dispatch_owner
            eventually(lambda: "subject" in owner.agents.blocked)
            repeat = harness.run_runtime_boot(setup[0])[0]
            assert repeat["operation_id"] == original["operation_id"] and repeat["reused"]
            assert calls == [1] and native.opens == 0
    deps, app = app_for(tmp_path / "home")
    with TestClient(app):
        current = deps.runtime_boot_status
        assert len(current) == 1 and current[0]["state"] == "blocked", current
        assert calls == [1]
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1
            assert uow.connection.execute("SELECT operation_id FROM execution_operations").fetchone()[0] == original["operation_id"]
