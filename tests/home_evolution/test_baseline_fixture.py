"""PR-00 validates reusable inputs and current queries, not HOME-R1 acceptance."""
import json
import math
from time import perf_counter

from .fixtures import BASE_AGENTS, OPERATOR, WORKSPACES, seed_scenario

pytest_plugins = ("home_evolution.fixtures",)


def test_global_identity_and_abc_activity_without_operator_messages(home_scenario):
    scenario = home_scenario
    alpha, beta = (scenario.graph_snapshot(workspace) for workspace in WORKSPACES)
    assert {n["agent_id"] for n in alpha["nodes"]} == set(BASE_AGENTS)
    assert {n["agent_id"] for n in beta["nodes"]} == set(BASE_AGENTS)
    assert {(e["from"], e["to"]) for e in alpha["edges"]["messages"]} == {("A", "B"), ("B", "C")}
    assert {(e["from"], e["to"]) for e in beta["edges"]["messages"]} == {("C", "A")}
    with scenario.factory.unit_of_work(write=False) as uow:
        c = uow.connection
        assert c.execute("SELECT COUNT(*) FROM messages WHERE from_agent_id='operator'").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM sessions WHERE agent_id='global'").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM sessions WHERE agent_id='A'").fetchone()[0] == 2
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []


def test_attempts_remain_distinct_from_work_and_session(home_scenario):
    scenario = home_scenario
    with scenario.factory.unit_of_work(write=False) as uow:
        c = uow.connection
        rows = c.execute("SELECT attempt_id,state,active,operation_id FROM handoff_runtime_attempts ORDER BY attempt_id").fetchall()
        assert [r["state"] for r in rows] == ["NOT_AVAILABLE", "CANCELLED_NO_EFFECT", "WAITING"]
        assert sum(r["active"] for r in rows) == 1
        assert all(r["operation_id"] is None for r in rows)
        assert c.execute("SELECT COUNT(*) FROM handoffs WHERE handoff_id='fixture-handoff-0000'").fetchone()[0] == 1
        actual = scenario.graph.handoffs(uow, workspace_id=WORKSPACES[0], handoff_id="fixture-handoff-0000")
        assert len(actual) == 1 and actual[0]["status"] == "OPEN"
        assert "runtime_progress" in actual[0]


def test_observation_ttl_uses_clock_without_mutating_history(home_scenario):
    scenario = home_scenario
    fresh = scenario.observations.read(context=OPERATOR)["items"][0]
    assert fresh["activity_state"] == "working" and fresh["freshness"] != "stale"
    before = scenario.counts()
    scenario.advance(120)
    stale = scenario.observations.read(context=OPERATOR)["items"][0]
    assert stale["freshness"] == "stale" and stale["activity_state"] == "unknown"
    assert stale["last_report"] == fresh["last_report"]
    assert scenario.counts() == before


def test_success_does_not_erase_cleanup_or_revoked_identity(home_scenario):
    scenario = home_scenario
    with scenario.factory.unit_of_work(write=False) as uow:
        c = uow.connection
        row = c.execute("SELECT r.stage,s.lifecycle_state,s.lease_state,k.state,k.release_proof_json "
            "FROM execution_receipts r JOIN execution_operations o USING(server_id,executor_id,operation_id) "
            "JOIN execution_sessions s USING(server_id,executor_id,session_id) "
            "JOIN execution_session_containment k USING(server_id,executor_id,session_id) "
            "WHERE r.operation_id='fixture-success'").fetchone()
        assert tuple(row) == ("SUCCEEDED", "READY", "ACTIVE", "REQUESTED", None)
        assert c.execute("SELECT is_active,permissions FROM agents WHERE agent_id='revoked'").fetchone()[0] == 0
    revoked = next(n for n in scenario.graph_snapshot()["nodes"] if n["agent_id"] == "revoked")
    assert revoked["is_active"] is False


def _measure(scenario, reader, *, samples=20):
    """Local warm SQLite/application + JSON encoding; no HTTP or browser render."""
    elapsed, encoding, query_counts, sizes = [], [], [], []
    with scenario.factory.unit_of_work(write=False) as uow:
        c = uow.connection
        reader(uow)  # Explicit warmup; excluded from measurements.
        changes = c.total_changes
        for _ in range(samples):
            queries = []
            c.set_trace_callback(lambda statement: queries.append(statement.split(None, 1)[0]))
            try:
                start = perf_counter()
                value = reader(uow)
                elapsed.append((perf_counter() - start) * 1000)
            finally:
                c.set_trace_callback(None)
            start = perf_counter()
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            encoding.append((perf_counter() - start) * 1000)
            query_counts.append(len(queries))
            sizes.append(len(encoded))
        assert c.total_changes == changes
    def stats(values):
        ordered = sorted(values)
        return {"p50_ms": ordered[len(ordered) // 2], "p95_ms": ordered[math.ceil(.95 * len(ordered)) - 1]}
    return {"samples": samples, "warmup": 1, "read": stats(elapsed), "json_encode": stats(encoding),
            "sql_statements_min": min(query_counts), "sql_statements_max": max(query_counts),
            "response_bytes_min": min(sizes), "response_bytes_max": max(sizes),
            "database_changes": 0, "browser_render_measured": False}


def test_current_graph_baseline_is_read_only(home_scenario, record_property):
    scenario = home_scenario
    measurement = _measure(scenario, lambda uow: scenario.graph.graph_snapshot(uow, workspace_id=WORKSPACES[0]))
    record_property("baseline_graph", json.dumps(measurement, sort_keys=True))
    assert measurement["sql_statements_min"] == measurement["sql_statements_max"]


def test_scale_100_agents_1000_inputs_100000_events_is_bounded_read(
        migrated_factory, tmp_config, fake_clock, record_property):
    scenario = seed_scenario(migrated_factory, tmp_config, fake_clock,
                             agents=100, activities=1000, events=100000)
    counts = scenario.counts()
    assert counts == dict(agents=100, workspaces=2, sessions=4, handoffs=1000,
                         handoff_runtime_attempts=3, events=100001)
    def page(uow):
        return scenario.graph.events_page(uow, workspace_id=WORKSPACES[0], stream="home-fixture", limit=10)
    with scenario.factory.unit_of_work(write=False) as uow:
        rows = page(uow)
        assert len(rows) == 10
        assert all(row["workspace_id"] == WORKSPACES[0] for row in rows)
        second = scenario.graph.events_page(uow, workspace_id=WORKSPACES[0], stream="home-fixture",
            limit=10, cursor=rows[-1]["event_id"])
        assert len(second) == 10
        assert {row["event_id"] for row in rows}.isdisjoint(row["event_id"] for row in second)
        assert uow.connection.execute("PRAGMA foreign_key_check").fetchall() == []
    measurement = _measure(scenario, page)
    measurement["fixture_counts"] = counts
    measurement["rows_per_read"] = 10
    record_property("baseline_existing_events_page", json.dumps(measurement, sort_keys=True))
    assert measurement["response_bytes_max"] < 10000
