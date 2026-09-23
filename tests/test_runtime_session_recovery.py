"""Production opening/restart fences; no providers or personal sessions."""
import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.harness import build_dispatcher
from okto_nexus.application.runtime_shutdown import shutdown_runtime
from test_pr34_remediation import runtime as runtime_fixture, open_rest

runtime = runtime_fixture


def test_revoked_binding_during_constructor_does_not_start_peer(runtime):
    deps = runtime[0]
    original = deps.harness_connector_factories["pi"]
    peers = []
    def construct(**kwargs):
        peer = original(**kwargs)
        peers.append(peer)
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agent_endpoints SET enabled=0,revision=revision+1 WHERE endpoint_id='endpoint-pi'")
        return peer
    deps.harness_connector_factories["pi"] = construct
    response = open_rest(runtime)
    assert response.status_code == 409, response.text
    assert peers[0].session is None, "revoked binding still spawned a native runtime"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM harness_sessions").fetchone()[0] == 0


def test_open_without_client_key_reserves_before_constructor(runtime):
    deps = runtime[0]
    original = deps.harness_connector_factories["pi"]
    observed = []

    def construct(**kwargs):
        with deps.connection_factory.unit_of_work(write=False) as uow:
            observed.extend(dict(r) for r in uow.connection.execute("SELECT * FROM runtime_open_requests"))
        assert observed and observed[0]["status"] == "RESERVED", "native construction preceded durable STARTING"
        return original(**kwargs)

    deps.harness_connector_factories["pi"] = construct
    response = open_rest(runtime)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["request_id"] == observed[0]["request_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT * FROM harness_sessions").fetchone()
        assert row["owner_epoch"] == deps.runtime_dispatcher.epoch
        assert observed[0]["endpoint_id"] == row["endpoint_id"]
        assert observed[0]["owner_epoch"] == row["owner_epoch"]


def test_unfinished_start_is_quarantined_without_replay(runtime):
    deps = runtime[0]
    dispatcher, supervisor = deps.runtime_dispatcher, deps.harness_supervisor
    from okto_nexus.adapters.outbound.sqlite.runtime_requests_repo import SqliteRuntimeRequestRepo
    from okto_nexus.adapters.outbound.sqlite.endpoints_repo import SqliteEndpointRepo
    with deps.connection_factory.unit_of_work() as uow:
        repo = SqliteEndpointRepo()
        endpoint = repo.get(uow, "endpoint-pi")
        rid, _ = SqliteRuntimeRequestRepo().reserve(uow, actor_id="operator", key="crash-before-spawn",
            request_hash="fixture", now=deps.clock.now_iso(), endpoint=endpoint,
            profile=repo.profile(uow, endpoint["profile_id"]), owner=(dispatcher.owner_id, dispatcher.epoch))
    shutdown_runtime(dispatcher, supervisor)
    recovered = bootstrap({}, ["--home", str(deps.config.home_dir)])
    recovered.config.feature_harness_integrations = True
    recovered.harness_connector_factories = deps.harness_connector_factories
    new = build_dispatcher(recovered)
    assert new.start()
    try:
        with recovered.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT status FROM runtime_open_requests WHERE request_id=?", (rid,)).fetchone()[0] == "OUTCOME_UNKNOWN"
            assert repo.get(uow, "endpoint-pi")["health"] == "quarantined"
        assert not runtime[3]
    finally:
        shutdown_runtime(new, recovered.harness_supervisor)


def test_restart_expires_only_old_runtime_presence_and_quarantines_binding(runtime):
    deps = runtime[0]
    opened = open_rest(runtime).json()["data"]
    sid = opened["session_id"]
    supervisor, old = deps.harness_supervisor, deps.runtime_dispatcher
    with deps.connection_factory.unit_of_work() as uow:
        presence = uow.connection.execute("SELECT presence_session_id,workspace_id FROM harness_sessions WHERE session_id=?", (sid,)).fetchone()
        deps.repos.sessions.create(uow, session_id="independent-presence", agent_id="worker",
            workspace_id=presence["workspace_id"], status="active", started_at=deps.clock.now_iso(), session_secret="fixture")
    # Close all test resources, then restore exactly the persisted crash cut.
    # This tests restart interpretation, not OS SIGKILL (qualified separately).
    shutdown_runtime(old, supervisor)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE harness_sessions SET status='RUNNING',lifecycle_state='protocol_ready',ended_at=NULL WHERE session_id=?", (sid,))
        uow.connection.execute("UPDATE sessions SET status='active',closed_at=NULL WHERE session_id=?", (presence["presence_session_id"],))
    recovered = bootstrap({}, ["--home", str(deps.config.home_dir)])
    recovered.config.feature_harness_integrations = True
    launches = []
    def forbidden(**kwargs):
        launches.append(kwargs)
        pytest.fail("restart must not silently replay or resume")
    recovered.harness_connector_factories = {k: forbidden for k in ("pi", "codex", "claude_code")}
    dispatcher = build_dispatcher(recovered)
    assert dispatcher.start()
    try:
        with recovered.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM harness_sessions WHERE session_id=?", (sid,)).fetchone()
            assert row["lifecycle_state"] == "unknown", "historical readiness survived owner loss"
            assert row["ended_at"] is None, "owner loss is not observed native end"
            assert uow.connection.execute("SELECT status FROM sessions WHERE session_id=?", (presence["presence_session_id"],)).fetchone()[0] == "closed"
            assert uow.connection.execute("SELECT status FROM sessions WHERE session_id='independent-presence'").fetchone()[0] == "active"
            endpoint = uow.connection.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='endpoint-pi'").fetchone()
            assert endpoint["health"] == "quarantined" and endpoint["health_reason"] == "owner_lost"
            assert dispatcher.repo.live_sessions(uow, endpoint_id="endpoint-pi") == []
        assert not launches
    finally:
        shutdown_runtime(dispatcher, recovered.harness_supervisor)
