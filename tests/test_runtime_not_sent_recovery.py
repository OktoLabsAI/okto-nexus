"""Proven pre-write rejection can return the original delivery to canonical pull."""
import json
from pathlib import Path

import pytest

from okto_nexus.application.auth import AgentKeyAuthService
from test_pr34_remediation import runtime as runtime_fixture, send_message, tool
from test_runtime_effective_capabilities import configure_codex
from test_runtime_operation_reconciliation import recovery
from test_runtime_outbox import wait_status

runtime = runtime_fixture


def rejected_before_write(runtime):
    _, client, _, _, operator, _ = runtime
    configure_codex(runtime, version="99.0.0")
    for adapter in ("pi", "claude_code.stream", "claude_code.attach"):
        response = client.patch(f"/api/v1/harness/endpoints/endpoint-{adapter}",
            headers={"x-api-key": operator}, json={"expected_revision": 1, "enabled": False})
        assert response.status_code == 200, response.text
    sent = send_message(runtime)
    return sent, wait_status(runtime, sent["runtime_operations"][0], "REJECTED")


@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_proven_not_sent_release_preserves_transport_evidence_and_original_inbox(runtime, surface):
    deps, client, root, _, operator, caller = runtime
    sent, row = rejected_before_write(runtime)
    assert row["reason"] == "native_write_not_started" and row["ack_level"] == "NONE"
    body = recovery(row, acknowledge_duplicate_risk=False)
    denied = tool(client, caller, "harness_list", {"view": "outbox", "maintenance": body})
    assert denied["error"]["code"] == "PERMISSION_DENIED"
    if surface == "rest":
        response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=body)
        assert response.status_code == 200, response.text
        result = response.json()["data"]
    else:
        response = tool(client, operator, "harness_list", {"view": "outbox", "maintenance": body})
        assert response["ok"], response
        result = response["data"]
    assert result["transport_state"] == "REJECTED"
    assert result["inbox_released"] and not result["native_replayed"]
    assert not result["duplicate_risk_acknowledged"] and not result["endpoint_quarantined"]
    repeated = tool(client, operator, "harness_list", {"view": "outbox", "maintenance": body})
    assert repeated["ok"] and repeated["data"] == result
    with deps.connection_factory.unit_of_work() as uow:
        worker_key = AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id="worker")
        current = deps.runtime_dispatcher.repo.get(uow, row["operation_id"])
        assert all(current[key] == row[key] for key in ("status", "reason", "ack_level", "attempt_id", "attempt_count"))
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
    pulled = tool(client, worker_key, "inbox_pull", {"agent_id": "worker"})
    assert pulled["ok"], pulled
    assert [item["message_id"] for item in pulled["data"]["messages"]] == [sent["message_id"]]
    wire = [json.loads(line) for line in (Path(root) / "capability-wire.jsonl").read_text().splitlines()]
    assert not any(item.get("request_method") == "turn/start" for item in wire)


@pytest.mark.parametrize("changed", [
    {"reason": "peer_rejected"}, {"ack_level": "TRANSPORT_WRITE"},
    {"status": "OUTCOME_UNKNOWN"}, {"native_turn_id": "observed-turn"},
    {"native_thread_id": "observed-thread"}, {"attempt_id": None},
])
def test_release_requires_complete_server_owned_non_delivery_proof(runtime, changed):
    deps, client, _, _, operator, _ = runtime
    _, row = rejected_before_write(runtime)
    # Mutate one persisted observation, not the caller's claimed identity.
    # No fabricated observation can weaken the uncertainty rule.
    with deps.connection_factory.unit_of_work() as uow:
        key, value = next(iter(changed.items()))
        uow.connection.execute(f"UPDATE delivery_outbox SET {key}=? WHERE operation_id=?", (value, row["operation_id"]))
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator},
        json=recovery(row | changed, acknowledge_duplicate_risk=False))
    assert response.status_code == 409, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT consumer_kind FROM message_deliveries WHERE delivery_id=?",
            (row["delivery_id"],)).fetchone()[0] == "push"
        assert uow.connection.execute("SELECT count(*) FROM runtime_operation_reconciliations").fetchone()[0] == 0


def test_safe_release_audit_and_inbox_roll_back_together(runtime, monkeypatch):
    from okto_nexus.errors import ErrorCode, OktoNexusError
    deps, client, _, _, operator, _ = runtime
    _, row = rejected_before_write(runtime)
    original = deps.repos.deliveries.release_runtime_reservation

    def cut(*args, **kwargs):
        original(*args, **kwargs)
        raise OktoNexusError(ErrorCode.CONFLICT, "Isolated commit cut", {})

    monkeypatch.setattr(deps.repos.deliveries, "release_runtime_reservation", cut)
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator},
        json=recovery(row, acknowledge_duplicate_risk=False))
    assert response.status_code == 409
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT consumer_kind FROM message_deliveries WHERE delivery_id=?",
            (row["delivery_id"],)).fetchone()[0] == "push"
        current = deps.runtime_dispatcher.repo.get(uow, row["operation_id"])
        assert current["reconciliation_id"] is None and current["status"] == "REJECTED"
        assert uow.connection.execute("SELECT count(*) FROM runtime_operation_reconciliations").fetchone()[0] == 0
