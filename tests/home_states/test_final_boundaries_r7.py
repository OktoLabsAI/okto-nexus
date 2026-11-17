"""Seven supplementary boundaries; no provider/browser qualification implied.

A06 covers the actual SQLite reader's complete private proof under a visual
filter, not a new live lease or end-to-end Working fixture. Results captures and
artifact links are explicitly migrated historical read inputs. H07 uses the
existing canonical native-request owner; its only intentional effect is own
grant revocation. Seen is an auxiliary preference, never an inbox ACK.
"""

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from okto_nexus.adapters.outbound.sqlite.home_entries import SqliteHomeEntryRelations
from okto_nexus.bootstrap.home_entries import install_home_entries
from okto_nexus.domain.attention import instant
from tests.execution_r4.test_native_decisions import decision_state
from tests.home_evolution.fixtures import WORKSPACES, home_scenario
from tests.home_evolution.test_home_boundaries import completed_handoffs
from tests.home_evolution.test_home_final_scope import copy_row
from tests.home_evolution.test_home_http import http
from tests.home_evolution.test_home_queries import link_handoff, service
from tests.home_states.test_productive_progress_propagation import seed_progress
from tests.home_states.test_projection_batch import authorized
from tests.home_states.test_projection_batch import scenario as query_scenario
from tests.home_states.test_results_boundary_completion import _productive_rows
from test_open_bootstrap import opening

__all__ = ["decision_state", "home_scenario", "http", "opening", "query_scenario", "service"]


def wired(request):
    scenario = request.getfixturevalue("home_scenario")
    projection = request.getfixturevalue("service")
    transport = request.getfixturevalue("http")
    transport.app.state.home = projection
    transport.app.state.attention = projection.attention
    install_home_entries(transport.app, projection)
    return scenario, transport.client


def get(client, route, **params):
    response = client.get("/api/v1/home/" + route, params=params)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()["data"]


def capture(scenario, *, stage="SUCCEEDED", text="Supplement partial output", at=None):
    """Schema-valid historical capture, not a fabricated canonical frame."""
    at = at or scenario.clock.now_iso()
    with scenario.factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("UPDATE execution_receipts SET stage=?,received_at=? WHERE operation_id='fixture-success'", (stage, at))
        c.execute(
            "INSERT INTO execution_event_ingress VALUES('fixture-server','fixture-executor',"
            "'fixture-native-session','supplement-history',1,'supplement-read-fixture','turn_state','{}',?)", (at,),
        )
        c.execute(
            "INSERT INTO execution_results(server_id,executor_id,operation_id,session_id,stream_epoch,"
            "terminal_sequence,output_text,output_truncated,output_event_count,delivery_outcome,captured_at) "
            "VALUES('fixture-server','fixture-executor','fixture-success','fixture-native-session',"
            "'supplement-history',1,?,0,1,?,?)",
            (text, {"SUCCEEDED": "success", "FAILED": "failed", "CANCELLED": "interrupted"}[stage], at),
        )


def result_for(client):
    value = get(client, "results", workspace_id=WORKSPACES[0], limit=100)
    assert value["status"] == "ready" and value["total_is_exact"]
    return next(item for item in value["items"] if item["source_ref"]["id"] == "fixture-success")


def test_a06_visual_filter_keeps_complete_private_sibling_proof(request):
    """Reader-level clause only: no invented lease/live Working assertion."""
    s = request.getfixturevalue("query_scenario")
    ids = seed_progress(s, count=2)
    queries = SqliteHomeEntryRelations()
    baseline = _productive_rows(s.factory)
    with authorized(s, {"workspace_id": "ws", "agent_id": "operator"}, 2) as (
        uow, scope, server, now, attention, params,
    ):
        changes = uow.connection.total_changes
        visible = queries._work(uow, params=params, attention_relation=attention)
        assert not any(ref["operation_id"] in ids for item in visible for ref in item["runtime_refs"])
        relation = queries.read(uow, scope=scope, server_id=server, now=now,
            attention_relation=attention, presentation_version=2)
        private = {row["operation_id"]: row for row in relation.harness_blocking if row["family"] == "operation"}
        assert ids <= private.keys()
        assert all(private[identifier].get("productive_progress_current") is True for identifier in ids)
        assert all(private[identifier]["workspace_id"] == "ws" for identifier in ids)
        assert relation.source_status["work"] == "ready" and uow.connection.total_changes == changes
    assert _productive_rows(s.factory) == baseline


@pytest.mark.parametrize("stage,outcome", [("FAILED", "failed"), ("CANCELLED", "cancelled")])
def test_e08_e09_partial_capture_remains_readable_at_exact_unsuccessful_target(request, stage, outcome):
    s, client = wired(request)
    marker = "Supplement partial output before " + stage
    capture(s, stage=stage, text=marker)
    baseline = _productive_rows(s.factory)
    result = result_for(client)
    target = {"kind": "result", "server_id": "fixture-server", "executor_id": "fixture-executor",
        "workspace_id": WORKSPACES[0], "session_id": "fixture-native-session", "operation_id": "fixture-success"}
    assert result["detail_target"] == target and result["outcome"] == stage
    assert result["preview"] == marker and result["truncated"] is False
    semantics = result["delivery_semantics"]
    assert semantics["execution_outcome"] == outcome and semantics["content_state"] == "available"
    assert semantics["task_state"] == semantics["verification"] == "not_applicable"
    assert semantics["verification_evidence_ref"] is None
    resolved = get(client, "target", workspace_id=WORKSPACES[0], target=json.dumps(target))
    assert resolved["available"] and resolved["target"] == target
    assert result_for(client) == result
    assert _productive_rows(s.factory) == baseline


def test_e16_offpage_seen_three_links_retention_and_no_inbox_ack(request):
    s, client = wired(request)
    completed_handoffs(s)
    link_handoff(s)
    old = (instant(s.clock.now_iso()) - timedelta(days=2)).isoformat(timespec="microseconds").replace("+00:00", "Z")
    capture(s, at=old)
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("UPDATE handoffs SET status='COMPLETED' WHERE handoff_id='fixture-handoff-0000'")
        c.execute("UPDATE handoffs SET status='COMPLETED',result='Other off-page delivery',claim_epoch=1 "
                  "WHERE handoff_id='fixture-handoff-0004'")
        operation = c.execute("SELECT * FROM execution_operations WHERE operation_id='fixture-success'").fetchone()
        receipt = c.execute("SELECT * FROM execution_receipts WHERE operation_id='fixture-success'").fetchone()
        captured = c.execute("SELECT * FROM execution_results WHERE operation_id='fixture-success'").fetchone()
        for index in range(3):
            native_operation = "fixture-success" if index == 0 else f"supplement-artifact-turn-{index}"
            if index:
                # One runtime_result per operation. The complete same-claim
                # grouping, not duplicate rows for one operation, owns files.
                copy_row(c, "execution_operations", operation, operation_id=native_operation)
                copy_row(c, "execution_receipts", receipt, operation_id=native_operation)
                c.execute("INSERT INTO execution_domain_deliveries VALUES('fixture-server','fixture-executor',?,'domain-work')",
                          (native_operation,))
                c.execute("INSERT INTO execution_event_ingress VALUES('fixture-server','fixture-executor',"
                          "'fixture-native-session','supplement-history',?,?,'turn_state','{}',?)",
                          (index + 1, "supplement-artifact-event-" + str(index), old))
                copy_row(c, "execution_results", captured, operation_id=native_operation, terminal_sequence=index + 1)
            artifact = f"supplement-artifact-{index}"
            uow.connection.execute(
                "INSERT INTO artifacts(artifact_id,workspace_id,artifact_type,name,path,created_at) "
                "VALUES(?,?,'file',?,'never-public-supplement-path',?)", (artifact, WORKSPACES[0], artifact + ".txt", old),
            )
            uow.connection.execute(
                "INSERT INTO runtime_results(result_id,payload,captured_at,operation_id,canonical_server_id,"
                "canonical_executor_id,canonical_operation_id,output_artifact_id) "
                "VALUES(?,'{}',?,'domain-work','fixture-server','fixture-executor',?,?)",
                ("supplement-link-" + str(index), old, native_operation, artifact),
            )
    baseline = _productive_rows(s.factory)
    first = get(client, "results", workspace_id=WORKSPACES[0], limit=1)
    selected = next(item for item in get(client, "results", workspace_id=WORKSPACES[0], limit=100)["items"]
        if item["source_ref"]["id"] == "fixture-handoff-0000")
    assert selected["created_at"] == old and instant(selected["created_at"]) < instant(s.clock.now_iso()) - timedelta(hours=24)
    assert selected["detail_target"]["operation_id"] in {"fixture-success", "supplement-artifact-turn-1", "supplement-artifact-turn-2"}
    assert selected["id"] not in {item["id"] for item in first["items"]}
    assert selected["view_state"] == "unseen" and first["next_cursor"]
    reached, cursor = list(first["items"]), first["next_cursor"]
    for _ in range(5):
        if cursor is None:
            break
        page = get(client, "results", workspace_id=WORKSPACES[0], limit=1, cursor=cursor)
        reached.extend(page["items"])
        cursor = page["next_cursor"]
    assert cursor is None and sum(item["id"] == selected["id"] for item in reached) == 1
    assert [a["artifact_id"] for a in selected["artifacts"]] == [f"supplement-artifact-{i}" for i in range(3)]
    assert "never-public-supplement-path" not in json.dumps(reached)
    other_before = {item["id"]: item["view_state"] for item in reached if item["id"] != selected["id"]}
    project_b = get(client, "results", workspace_id=WORKSPACES[1], limit=100)["items"]

    def deliveries():
        board = get(client, "harness-board", workspace_id=WORKSPACES[0], presentation_version=2, limit=100)
        assert board["columns"]["results"]["total_is_exact"]
        return {item["result"]["id"] for item in board["columns"]["results"]["items"] if item.get("result")}

    assert selected["id"] in deliveries()
    occurrence = selected["attention"]
    assert occurrence is not None
    response = client.post("/api/v1/attention/" + occurrence["attention_id"] + "/seen", json={
        "source_revision": occurrence["source_revision"], "preference_revision": occurrence["seen_state"]["revision"],
        "seen": True,
    })
    assert response.status_code == 200, response.text
    fresh = get(client, "results", workspace_id=WORKSPACES[0], limit=100)["items"]
    assert next(item for item in fresh if item["id"] == selected["id"])["view_state"] == "seen"
    assert {item["id"]: item["view_state"] for item in fresh if item["id"] != selected["id"]} == other_before
    assert get(client, "results", workspace_id=WORKSPACES[1], limit=100)["items"] == project_b
    assert selected["id"] not in deliveries()
    stale = client.get("/api/v1/home/results", params={"workspace_id": WORKSPACES[0], "limit": 1,
        "cursor": first["next_cursor"]})
    assert stale.status_code == 409, stale.text
    exact = get(client, "target", workspace_id=WORKSPACES[0], target=json.dumps(selected["detail_target"]))
    assert exact["available"] and exact["target"] == selected["detail_target"]
    assert _productive_rows(s.factory) == baseline  # Includes message_deliveries: no ACK.


def test_h02_forged_exact_targets_disclose_no_preview_or_counter(request):
    s, client = wired(request)
    marker = "SUPPLEMENT_PROTECTED_OUTPUT"
    capture(s, text=marker)
    result = result_for(client)
    assert result["preview"] == marker
    target = result["detail_target"]
    baseline = _productive_rows(s.factory)
    for changes, workspace, expected in (
        ({"server_id": "not-this-server"}, WORKSPACES[0], 409),
        ({}, WORKSPACES[1], 409),
        ({"session_id": "not-this-session"}, WORKSPACES[0], 404),
        ({"operation_id": "not-this-operation"}, WORKSPACES[0], 404),
    ):
        response = client.get("/api/v1/home/target", params={
            "target": json.dumps(target | changes), "workspace_id": workspace,
        })
        assert response.status_code == expected, response.text
        error = response.json()
        assert "data" not in error and error["ok"] is False
        assert marker not in response.text and "preview" not in response.text and "summary" not in response.text
    assert _productive_rows(s.factory) == baseline


def test_h03_http_hostile_public_label_does_not_expose_private_marker(request):
    """JSON minimization only; actual DOM/ANSI execution belongs to browser."""
    s = request.getfixturevalue("query_scenario")
    public = '<img src=x onerror="hst_public_marker=true">'
    secret = "HST_SUPPLEMENT_PRIVATE_TOKEN"
    with s.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE workspaces SET display_name=? WHERE workspace_id='ws'",
            (public + "\x1b[31m\nBearer " + secret,))
    baseline = _productive_rows(s.factory)
    client = TestClient(s.app, headers={"Authorization": "Bearer " + s.app.state.test_agent_keys["operator"]})
    try:
        response = client.get("/api/v1/home/harness-board", params={"presentation_version": 2, "limit": 100})
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/json")
        data = response.json()["data"]
        cards = [item for lane in data["columns"].values() for item in lane["items"] if item["kind"] == "harness"]
        labels = [item["connection"]["workspace_label"] for item in cards if item["connection"]["workspace_id"] == "ws"]
        assert labels and all(isinstance(label, str) and len(label) <= 160 for label in labels)
        assert all("hst_public_marker" in label for label in labels)
        assert secret not in response.text and "private-marker" not in response.text
        assert "\x1b" not in response.text and "\n" not in "".join(labels)
    finally:
        client.close()
    assert _productive_rows(s.factory) == baseline


@pytest.mark.parametrize("decision_state", ["input"], indirect=True)
def test_h07_revoked_scope_refuses_same_cas_and_keeps_exact_history(decision_state):
    deps, app, body = decision_state
    client = TestClient(app, headers={"Authorization": "Bearer " + app.state.test_agent_keys["operator"]})
    try:
        key = body["approval_key"]
        before = get(client, "work", workspace_id=key["workspace_id"], state="all", limit=100)
        target = next(item["detail_target"] for item in before["items"]
            if item["detail_target"].get("session_id") == key["session_id"])
        assert target["server_id"] == key["server_id"] and target["executor_id"] == key["executor_id"]
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at=?", (deps.clock.now_iso(),))
        baseline = _productive_rows(deps.connection_factory)
        response = client.post("/v1/runtime/approval-decisions", json=body)
        assert response.status_code in (403, 409), response.text
        assert "sensitive-input-marker" not in response.text
        history = get(client, "target", workspace_id=key["workspace_id"], target=json.dumps(target))
        assert history["available"] and history["target"] == target
        assert _productive_rows(deps.connection_factory) == baseline
    finally:
        client.close()
