"""Approved boot through the actual HTTP lifespan; synthetic external peers only."""
import asyncio

import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.harness import run_runtime_boot, build_access_service
from okto_nexus.application.runtime_shutdown import shutdown_runtime
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError
from test_pr34_remediation import runtime as runtime_fixture, open_rest

runtime = runtime_fixture


def configure(runtime, endpoint="endpoint-pi", key=None, revision=1):
    _, client, _, _, operator, _ = runtime
    return client.put(f"/api/v1/harness/endpoints/{endpoint}/boot", headers={"x-api-key": key or operator},
        json={"enabled": True, "expected_revision": revision})


def fresh(runtime):
    deps = runtime[0]
    shutdown_runtime(deps.runtime_dispatcher, deps.harness_supervisor)
    recovered = bootstrap({}, ["--home", str(deps.config.home_dir)])
    recovered.config.feature_harness_integrations = True
    recovered.harness_connector_factories = deps.harness_connector_factories.copy()
    return recovered


def test_stable_boot_preserves_identity_and_repeated_start_does_not_duplicate(runtime):
    assert configure(runtime).status_code == 200
    recovered = fresh(runtime)
    async def run():
        app = build_app(recovered)
        async with app.router.lifespan_context(app):
            first = recovered.runtime_boot_status
            assert first[0]["state"] == "protocol_ready", first
            second = run_runtime_boot(recovered)
            assert second[0]["session_id"] == first[0]["session_id"] and second[0]["reused"]
            assert len(runtime[3]) == 1
            with recovered.connection_factory.unit_of_work(write=False) as uow:
                agent = recovered.repos.agents.get(uow, "worker")
                assert agent.metadata == {"keep": "profile"} and agent.role == "reviewer"
                assert uow.connection.execute("SELECT count(*) FROM runtime_open_requests").fetchone()[0] == 1
    asyncio.run(run())


def test_one_failed_boot_does_not_prevent_other_endpoint(runtime):
    for endpoint in ("endpoint-pi", "endpoint-codex"):
        assert configure(runtime, endpoint).status_code == 200
    recovered = fresh(runtime)
    def failed(**kwargs):
        raise OSError("fixture binary missing")
    recovered.harness_connector_factories["pi"] = failed
    async def run():
        app = build_app(recovered)
        async with app.router.lifespan_context(app):
            states = {r["endpoint_id"]: r["state"] for r in recovered.runtime_boot_status}
            assert states == {"endpoint-codex": "protocol_ready", "endpoint-pi": "blocked"}
            assert len(recovered.harness_supervisor.list_live()) == 1
    asyncio.run(run())


@pytest.mark.parametrize("change", ["revoked", "profile_revision", "issuer_rotated", "quarantined"])
def test_boot_revalidates_approval_before_any_native_effect(runtime, change):
    assert configure(runtime).status_code == 200
    recovered = fresh(runtime)
    with recovered.connection_factory.unit_of_work() as uow:
        sql = {
            "revoked": "UPDATE runtime_boot_bindings SET enabled=0",
            "profile_revision": "UPDATE runtime_profiles SET revision=revision+1 WHERE profile_id='profile-pi'",
            "issuer_rotated": "UPDATE agents SET api_key_hash='fixture-rotated' WHERE agent_id='operator'",
            "quarantined": "UPDATE agent_endpoints SET health='quarantined' WHERE endpoint_id='endpoint-pi'",
        }[change]
        uow.connection.execute(sql)
    async def run():
        app = build_app(recovered)
        async with app.router.lifespan_context(app):
            assert not recovered.harness_supervisor.list_live()
            assert not runtime[3]
    asyncio.run(run())


def test_boot_authority_cannot_be_used_for_control_or_other_binding(runtime):
    deps = runtime[0]
    assert configure(runtime, key=runtime[5]).status_code == 403
    assert configure(runtime).status_code == 200
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='endpoint-pi'").fetchone()
    context = RuntimeRequestContext(actor_agent_id=None, authentication_source="runtime_boot",
        endpoint_id="endpoint-pi", workspace_id=row["workspace_id"], represented_agent_id="worker",
        runtime_owner_id=deps.runtime_dispatcher.owner_id, runtime_owner_epoch=deps.runtime_dispatcher.epoch)
    service = build_access_service(deps)
    service.authorize(context, action="open", endpoint_id="endpoint-pi")
    for action, endpoint in (("send", "endpoint-pi"), ("admin", "endpoint-pi"), ("open", "endpoint-codex")):
        with pytest.raises(OktoNexusError):
            service.authorize(context, action=action, endpoint_id=endpoint)


def test_endpoint_reconciliation_requires_explicit_risk_and_is_idempotent(runtime):
    deps, client, _, peers, key, caller = runtime
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET health='quarantined',health_reason='owner_lost' WHERE endpoint_id='endpoint-pi'")
    assert open_rest(runtime).status_code == 403 and not peers
    body = {"expected_revision": 1, "idempotency_key": "fixture-reconciliation", "reason": "Reviewed disposable fixture owner"}
    url = "/api/v1/harness/endpoints/endpoint-pi/reconcile"
    assert client.post(url, headers={"x-api-key": key}, json=body).status_code == 422
    body["acknowledge_uncertain_effects"] = True
    assert client.post(url, headers={"x-api-key": caller}, json=body).status_code == 403
    response = client.post(url, headers={"x-api-key": key}, json=body)
    assert response.status_code == 200, response.text
    repeated = client.post(url, headers={"x-api-key": key}, json=body)
    assert repeated.json()["data"]["reconciliation_id"] == response.json()["data"]["reconciliation_id"]
    assert repeated.json()["data"]["replayed"]
    assert not peers, "reconciliation must not itself spawn or replay"
    assert open_rest(runtime).status_code == 200
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_endpoint_reconciliations").fetchone()[0] == 1


def test_attach_pid_is_not_stable_boot_identity(runtime):
    response = configure(runtime, "endpoint-claude_code.attach")
    assert response.status_code == 422
    assert not runtime[3]


def test_failed_native_start_persists_quarantine_and_boot_cannot_replay(runtime):
    deps = runtime[0]
    original = deps.harness_connector_factories["pi"]
    starts = []
    def construct(**kwargs):
        peer = original(**kwargs)
        def start(**_):
            starts.append(1)
            raise OSError("fixture uncertain native handshake")
        peer.start = start
        return peer
    deps.harness_connector_factories["pi"] = construct
    assert configure(runtime).status_code == 200
    assert open_rest(runtime).status_code == 500
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT health FROM agent_endpoints WHERE endpoint_id='endpoint-pi'").fetchone()[0] == "quarantined"
    recovered = fresh(runtime)
    async def run():
        app = build_app(recovered)
        async with app.router.lifespan_context(app):
            assert recovered.runtime_boot_status[0]["state"] == "blocked"
    asyncio.run(run())
    assert starts == [1]


def test_global_boot_budget_defers_remaining_bindings_and_retains_stuck_slot(runtime):
    import threading
    import time
    from okto_nexus.application.runtime_boot import RuntimeBootService
    from okto_nexus.adapters.inbound.mcp.tools.harness import build_open_service, build_connector_factories
    from okto_nexus.adapters.outbound.sqlite.endpoints_repo import SqliteEndpointRepo
    deps = runtime[0]
    for endpoint in ("endpoint-codex", "endpoint-pi"):
        assert configure(runtime, endpoint).status_code == 200
    release, started = threading.Event(), threading.Event()
    original = deps.harness_connector_factories["codex"]
    def construct(**kwargs):
        peer = original(**kwargs)
        start = peer.start
        def blocked(**args):
            started.set()
            assert release.wait(5)
            return start(**args)
        peer.start = blocked
        return peer
    deps.harness_connector_factories["codex"] = construct
    service = RuntimeBootService(connection_factory=deps.connection_factory, endpoints=SqliteEndpointRepo(),
        registry=build_connector_factories(deps), open_service=build_open_service(deps),
        owner_id=deps.runtime_dispatcher.owner_id, owner_epoch=deps.runtime_dispatcher.epoch)
    began = time.monotonic()
    try:
        result = service.run(budget_seconds=.1)
        assert time.monotonic() - began < 1
        assert started.is_set()
        assert result[0]["state"] == "blocked" and result[1]["state"] == "deferred"
        assert len(runtime[3]) == 1 and not deps.harness_supervisor.list_live()
    finally:
        release.set()
