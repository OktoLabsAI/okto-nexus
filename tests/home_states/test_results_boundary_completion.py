"""Results boundaries over real ASGI/SQLite, without a native runtime/provider.

E10 uses canonical coordination tools. E12/E14/E15 use the existing migrated
historical-read fixture: its execution rows are synthetic, not Core ingress,
native prompts, real cancellation or evidence that a provider ran. Presentation
and browser assertions belong to separate qualification layers.
"""

import json

import pytest
from fastapi.testclient import TestClient

from okto_nexus.adapters.inbound.http.app import build_app
from tests.home_evolution.fixtures import WORKSPACES, home_scenario
from tests.home_evolution.test_home_final_scope import copy_row
from tests.home_evolution.test_home_http import http
from tests.home_evolution.test_home_queries import service
from tests.test_verification import _create, _ok, make_env

__all__ = ["home_scenario", "http", "service"]


# Auth telemetry is intentionally separate. These exact row snapshots include
# coordination, grants, Test/Finish, execution, capture and decision effects.
PRODUCTIVE_TABLES = (
    "connection_setup_commits", "execution_bindings", "agent_endpoints",
    "runtime_execution_grants", "messages", "message_deliveries", "handoffs",
    "sessions", "execution_sessions", "execution_operations", "execution_decisions",
    "execution_dispatch_outbox", "delivery_outbox", "runtime_handoff_bindings",
    "approvals", "connection_authorization_receipts", "execution_receipts",
    "runtime_native_approvals", "runtime_relay_decisions", "execution_results",
    "execution_event_ingress", "execution_event_watermarks", "runtime_results", "events",
)


def _productive_rows(factory):
    with factory.unit_of_work(write=False) as uow:
        return {
            table: sorted(
                (tuple(row) for row in uow.connection.execute("SELECT * FROM " + table)),
                key=repr,
            )
            for table in PRODUCTIVE_TABLES
        }


def _get(client, section, workspace_id):
    response = client.get(
        "/api/v1/home/" + section,
        params={"workspace_id": workspace_id, "limit": 100},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    page = response.json()["data"]
    assert page["status"] == "ready" and page["total_is_exact"]
    assert page["scope"]["workspace_id"] == workspace_id
    assert not page["has_more"] and page["next_cursor"] is None
    assert page["total"] == len(page["items"])
    return page


def _synthetic_http(request):
    scenario = request.getfixturevalue("home_scenario")
    projection = request.getfixturevalue("service")
    transport = request.getfixturevalue("http")
    # Same established HTTP fixture/middleware; only the read service is the
    # synthetic migrated dataset. No authorization or response is mocked.
    transport.app.state.home = projection
    return scenario, transport.client


def test_e10_canonical_rejected_handoff_without_native_result_has_no_native_outcome(tmp_path):
    deps, tools, root = make_env(
        tmp_path,
        extra={
            "OKTO_NEXUS_FEATURE_HARNESS_INTEGRATIONS": "false",
            "OKTO_NEXUS_EMBEDDING_MODE": "off",
        },
    )
    client = None
    try:
        created = _ok(_create(tools, root))
        handoff_id = created["handoff_id"]
        rejected = _ok(tools["handoff_reject"](
            project_root=root, handoff_id=handoff_id, agent_id="beta",
            reason="Synthetic recipient refusal; no native execution was requested",
        ))
        assert rejected["status"] == "REJECTED"
        with deps.connection_factory.unit_of_work(write=False) as uow:
            stored = uow.connection.execute(
                "SELECT * FROM handoffs WHERE handoff_id=?", (handoff_id,),
            ).fetchone()
            workspace = stored["workspace_id"]
            assert stored["status"] == "REJECTED" and stored["result"] is None
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_results").fetchone()[0] == 0
        # No second lifespan/runtime owner: this canonical tools fixture has
        # not started one, and these ASGI requests need only read services.
        client = TestClient(build_app(deps), client=("127.0.0.1", 50000), base_url="http://localhost")
        baseline = _productive_rows(deps.connection_factory)
        first = _get(client, "results", workspace)
        assert len(first["items"]) == 1
        result = first["items"][0]
        assert result["source_ref"]["type"] == "handoff_result"
        assert result["source_ref"]["id"] == handoff_id and result["outcome"] == "REJECTED"
        assert result["detail_target"] == {
            "kind": "handoff", "server_id": first["server_id"],
            "workspace_id": workspace, "handoff_id": handoff_id,
        }
        semantics = result["delivery_semantics"]
        assert semantics["scope"] == "handoff" and semantics["task_state"] == "rejected"
        assert semantics["execution_outcome"] == "not_applicable"
        assert semantics["verification"] == "not_applicable"
        assert semantics["verification_evidence_ref"] is None
        assert semantics["content_state"] == "not_captured" and not semantics["historical"]
        assert _get(client, "results", workspace)["items"] == first["items"]
        assert _productive_rows(deps.connection_factory) == baseline
    finally:
        if client is not None:
            client.close()
        deps.connection_factory.close()


def test_e12_historical_terminal_receipt_without_capture_is_ended_but_content_pending(request):
    scenario, client = _synthetic_http(request)
    with scenario.factory.unit_of_work(write=False) as uow:
        receipt = uow.connection.execute(
            "SELECT stage FROM execution_receipts WHERE operation_id='fixture-success'",
        ).fetchone()
        assert receipt["stage"] == "SUCCEEDED"
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_results").fetchone()[0] == 0
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_event_ingress").fetchone()[0] == 0
    baseline = _productive_rows(scenario.factory)
    first = _get(client, "results", WORKSPACES[0])
    assert len(first["items"]) == 1
    result = first["items"][0]
    assert result["source_ref"]["id"] == "fixture-success"
    assert result["outcome"] == "SUCCEEDED" and result["preview"] is None
    assert result["artifacts"] == [] and not result["truncated"]
    assert result["detail_target"] == {
        "kind": "result", "server_id": "fixture-server", "executor_id": "fixture-executor",
        "workspace_id": WORKSPACES[0], "session_id": "fixture-native-session",
        "operation_id": "fixture-success",
    }
    semantics = result["delivery_semantics"]
    assert semantics["scope"] == "turn" and semantics["execution_outcome"] == "succeeded"
    assert semantics["content_state"] == "pending" and semantics["cleanup"] == "pending"
    assert semantics["task_state"] == semantics["verification"] == "not_applicable"
    assert semantics["verification_evidence_ref"] is None
    assert _get(client, "results", WORKSPACES[0])["items"] == first["items"]
    assert _productive_rows(scenario.factory) == baseline


@pytest.mark.parametrize("free_text", [None, "Done: terminei", "verified"])
def test_e14_silence_idle_or_free_text_without_terminal_fact_never_invents_results(request, free_text):
    scenario, client = _synthetic_http(request)
    # Historical read-model inputs, not a fabricated canonical native frame.
    # READY alone has no productive progress/terminal proof. A message body is
    # ordinary coordination text, including words suggestive of completion.
    with scenario.factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("UPDATE execution_operations SET admission_state='DISPATCHED' WHERE operation_id='fixture-success'")
        c.execute("UPDATE execution_receipts SET stage='SUBMITTED' WHERE operation_id='fixture-success'")
        if free_text is not None:
            c.execute("UPDATE messages SET body=? WHERE message_id='fixture-message-0'", (free_text,))
            c.execute(
                "INSERT INTO events(workspace_id,stream,type,actor_agent_id,payload,visibility,created_at) "
                "VALUES(?,'message','message.created','A',?,'public',?)",
                (WORKSPACES[0], json.dumps({"message_id": "fixture-message-0", "body": free_text}),
                 scenario.clock.now_iso()),
            )
        assert c.execute("SELECT COUNT(*) FROM execution_results").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM execution_event_ingress").fetchone()[0] == 0
        assert c.execute(
            "SELECT COUNT(*) FROM execution_receipts WHERE stage IN ('SUCCEEDED','FAILED','CANCELLED')",
        ).fetchone()[0] == 0
        assert c.execute(
            "SELECT lifecycle_state FROM execution_sessions WHERE session_id='fixture-native-session'",
        ).fetchone()[0] == "READY"
    baseline = _productive_rows(scenario.factory)
    for _ in range(2):
        results = _get(client, "results", WORKSPACES[0])
        assert results["total"] == 0 and results["items"] == []
        work = _get(client, "work", WORKSPACES[0])
        current = next(item for item in work["items"] if item["source_ref"]["id"] == "fixture-success")
        assert current["display_state"] == "native_accepted" and current["running_count"] == 0
    assert _productive_rows(scenario.factory) == baseline


def test_e15_unknown_attempt_keeps_exact_monitorable_target_and_confirmed_history(request):
    scenario, client = _synthetic_http(request)
    confirmed = _get(client, "results", WORKSPACES[0])["items"]
    assert len(confirmed) == 1 and confirmed[0]["source_ref"]["id"] == "fixture-success"
    unknown_id = "hst-unknown-no-terminal"
    with scenario.factory.unit_of_work() as uow:
        c = uow.connection
        operation = c.execute("SELECT * FROM execution_operations WHERE operation_id='fixture-success'").fetchone()
        receipt = c.execute("SELECT * FROM execution_receipts WHERE operation_id='fixture-success'").fetchone()
        copy_row(c, "execution_operations", operation, operation_id=unknown_id, admission_state="RECONCILING")
        copy_row(c, "execution_receipts", receipt, operation_id=unknown_id,
                 stage="OUTCOME_UNKNOWN", possible_effect=1, retry_safe=0)
        assert c.execute(
            "SELECT COUNT(*) FROM execution_results WHERE operation_id=?", (unknown_id,),
        ).fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM execution_event_ingress").fetchone()[0] == 0
    baseline = _productive_rows(scenario.factory)
    for _ in range(2):
        results = _get(client, "results", WORKSPACES[0])
        assert results["items"] == confirmed and results["total"] == 1
        assert all(item["source_ref"]["id"] != unknown_id for item in results["items"])
        work = _get(client, "work", WORKSPACES[0])
        unknown = next(item for item in work["items"] if item["source_ref"]["id"] == unknown_id)
        assert unknown["display_state"] == "outcome_unknown" and unknown["evidence_status"] == "unknown"
        assert unknown["running_count"] == 0
        target = {
            "kind": "execution", "server_id": "fixture-server", "executor_id": "fixture-executor",
            "workspace_id": WORKSPACES[0], "session_id": "fixture-native-session", "operation_id": unknown_id,
        }
        assert unknown["detail_target"] == target
        response = client.get("/api/v1/home/target", params={
            "workspace_id": WORKSPACES[0], "target": json.dumps(target),
        })
        assert response.status_code == 200, response.text
        resolved = response.json()["data"]
        assert resolved["available"] and resolved["target"] == target and resolved["agent_id"] == "B"
    assert _productive_rows(scenario.factory) == baseline
