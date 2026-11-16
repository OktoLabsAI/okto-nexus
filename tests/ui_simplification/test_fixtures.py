"""UI-005 fixture facts only; no future product journey is promoted."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

PATH = Path(__file__).parents[2] / "NEXUS_UI_R1/execution/fixtures.py"
SPEC = importlib.util.spec_from_file_location("ui_r1_fixtures", PATH)
fixtures = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fixtures
SPEC.loader.exec_module(fixtures)


@pytest.fixture
def scenario(tmp_path):
    with fixtures.scenario(tmp_path / "scenario") as value:
        yield value


def test_clock_barrier_and_empty_directory_guard(tmp_path):
    clock = fixtures.ControlledClock()
    before = clock.now_epoch()
    clock.advance(2)
    assert clock.now_epoch() == before + 2
    assert clock.now_iso() == "2026-11-16T12:00:02.000000Z"
    barrier = fixtures.ReadBarrier()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(barrier.wait)
        assert barrier.entered.wait(2)
        assert not pending.done()
        barrier.release.set()
        assert pending.result(timeout=2) is None
    (tmp_path / "existing").write_text("owned by caller")
    with pytest.raises(ValueError, match="empty"):
        with fixtures.scenario(tmp_path):
            pytest.fail("must refuse existing inputs")


def test_one_installation_two_exact_connections_sessions(scenario):
    s = scenario
    with s.factory.unit_of_work(write=False) as uow:
        c = uow.connection
        installation = c.execute("SELECT server_id FROM execution_installation").fetchall()
        assert len(installation) == 1
        assert {x.server_id for x in s.connections} == {installation[0][0]}
        for fact, session_id in zip(s.connections, s.sessions, strict=True):
            row = c.execute("SELECT s.*,e.agent_id FROM execution_sessions s JOIN execution_bindings b USING(server_id,executor_id,binding_id) JOIN agent_endpoints e USING(endpoint_id) WHERE s.session_id=?", (session_id,)).fetchone()
            assert tuple(row[k] for k in ("server_id", "executor_id", "binding_id", "workspace_id", "workspace_binding_id", "agent_id")) == (
                fact.server_id, fact.executor_id, fact.binding_id, fact.workspace_id, fact.workspace_binding_id, fact.agent_id)
        assert c.execute("SELECT COUNT(*) FROM execution_sessions").fetchone()[0] == 2
        assert c.execute("SELECT COUNT(*) FROM execution_sessions WHERE lifecycle_state='READY'").fetchone()[0] == 1
        assert s.sessions[0] != s.sessions[1]
        assert s.connections[0].binding_id != s.connections[1].binding_id
        assert s.connections[1].provenance == "synthetic-read-fact"


def test_delegation_unassigned_uncertainty_cleanup_external_and_pages(scenario):
    s = scenario
    with s.factory.unit_of_work(write=False) as uow:
        c = uow.connection
        chain = c.execute("SELECT from_agent_id,target FROM handoffs WHERE handoff_id LIKE 'ui-handoff-%' ORDER BY handoff_id").fetchall()
        assert [(r[0], json.loads(r[1])["agent_id"]) for r in chain] == [("subject", "B"), ("B", "C")]
        assert c.execute("SELECT COUNT(*) FROM messages WHERE from_agent_id='operator'").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM runtime_handoff_bindings WHERE handoff_id='ui-unassigned'").fetchone()[0] == 0
        assert tuple(c.execute("SELECT stage,possible_effect,retry_safe FROM execution_receipts WHERE operation_id='ui-unknown'").fetchone()) == ("OUTCOME_UNKNOWN", 1, 0)
    results = s.read(section="results")
    success = next(x for x in results["items"] if x["detail_target"]["operation_id"] == "ui-success")
    assert success["cleanup_state"] == "pending"
    assert success["detail_target"]["session_id"] == s.sessions[1]
    full = s.read(section="work", filters={"state": "all"}, limit=100)
    rows, cursor = [], None
    while True:
        page = s.read(section="work", filters={"state": "all"}, limit=1, cursor=cursor)
        rows.extend(page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(rows) == full["total"] == len({x["id"] for x in rows})
    assert {x["id"] for x in rows} == {x["id"] for x in full["items"]}
    unassigned = next(x for x in rows if x["detail_target"].get("handoff_id") == "ui-unassigned")
    assert not unassigned["runtime_refs"]
    assert any(x["detail_target"].get("operation_id") == "ui-unknown" for x in rows)
    external = s.read()["external_activity"]
    assert external["status"] == "ready" and external["total"] == 1
    assert s.external["observed_instance_id"] in json.dumps(external)


@pytest.mark.parametrize("recipient,display", [("operator", "awaiting_operator"), ("subject", "awaiting_agent")])
def test_canonical_question_recipient_authority(tmp_path, recipient, display):
    with fixtures.scenario(tmp_path / "question", recipient=recipient) as s:
        work = s.read(section="work", filters={"state": display})
        assert work["total"] == 1
        assert work["items"][0]["detail_target"]["session_id"] == s.sessions[0]
        assert "private-marker" not in json.dumps(work)
        client = TestClient(s.app)  # Existing opening context owns lifespan/WSS.
        try:
            for actor in ("operator", "subject", "other"):
                headers = {"Authorization": "Bearer " + s.app.state.test_agent_keys[actor]}
                response = client.get("/v1/runtime/input-requests", headers=headers)
                assert response.status_code == 200
                assert len(response.json()["items"]) == (1 if actor == recipient else 0)
                if actor != recipient:
                    assert client.post("/v1/runtime/approval-decisions", json=s.decision_body, headers=headers).status_code == 403
        finally:
            client.close()


def test_partial_source_is_not_empty_success(scenario):
    with scenario.partial_work():
        view = scenario.read()
        assert view["work"]["status"] == "unavailable"
        assert view["work"]["total"] is None
        assert view["summary"]["running"]["value"] is None
        assert view["results"]["status"] == "ready"
        assert view["external_activity"]["status"] == "ready"
    assert scenario.read()["work"]["status"] == "ready"


def test_single_current_baseline_sample(scenario, record_property):
    sample = scenario.baseline()
    assert sample["samples"] == 1
    assert sample["read_uows"] == 1 and sample["all_read_only"]
    assert sample["writes"] == 0
    assert sample["sql_statements"] > 0 and sample["payload_bytes"] > 0
    assert set(sample["sections"].values()) == {"ready"}
    record_property("current_home_baseline", json.dumps(sample, sort_keys=True))
    print("UI005_BASELINE=" + json.dumps(sample, sort_keys=True))
