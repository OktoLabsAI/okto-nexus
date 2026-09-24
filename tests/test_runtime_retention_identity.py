"""Operator retention/deactivation must retain transport exclusion and dedupe."""
import pytest

from okto_nexus.domain.base import iso_plus
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_outbox import wait_status
from test_runtime_commands import wait_operation, wait_close_result

runtime = runtime_fixture


@pytest.mark.parametrize("uncertain", [False, True])
def test_prune_and_agent_deactivation_preserve_pending_transport_fences(runtime, monkeypatch, uncertain):
    deps, client, _, peers, operator, _ = runtime
    headers = {"x-api-key": operator}
    assert open_rest(runtime).status_code == 200
    if uncertain:
        original = peers[0].send

        def lost_reply(session, command):
            original(session, command)
            if command.verb == "send_turn":
                raise OSError("fixture write outcome lost")

        monkeypatch.setattr(peers[0], "send", lost_reply)
    else:
        # Pause only dispatch, retaining the production owner/maintenance.
        monkeypatch.setattr(deps.runtime_dispatcher, "scan_once", lambda: None)
    source = send_message(runtime, body="retention pending fixture")
    op = source["runtime_operations"][0]
    row = wait_status(runtime, op, "OUTCOME_UNKNOWN" if uncertain else "PENDING")
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE messages SET created_at='2000-01-01T00:00:00.000000Z' WHERE message_id=?",
            (source["message_id"],))
        deps.repos.messages.create(uow, message_id="unrelated-expired", workspace_id=source["workspace_id"],
            from_agent_id="caller", created_at="2000-01-01T00:00:00.000000Z")
        before = {table: [dict(r) for r in uow.connection.execute(f"SELECT * FROM {table}")]
            for table in ("delivery_outbox", "message_deliveries", "runtime_delivery_attempt_events", "runtime_message_causality")}
    disabled = client.patch("/api/v1/agents/worker", headers=headers, json={"is_active": False})
    assert disabled.status_code == 200, disabled.text
    for _ in range(2):
        pruned = client.post("/api/v1/admin/prune?dry_run=false", headers=headers)
        assert pruned.status_code == 200, pruned.text
    with deps.connection_factory.unit_of_work() as uow:
        assert not deps.repos.agents.get(uow, "worker").is_active
        assert uow.connection.execute("SELECT 1 FROM messages WHERE message_id=?", (source["message_id"],)).fetchone()
        assert not uow.connection.execute("SELECT 1 FROM messages WHERE message_id='unrelated-expired'").fetchone()
        for table, rows in before.items():
            assert [dict(r) for r in uow.connection.execute(f"SELECT * FROM {table}")] == rows, table
        assert not deps.repos.deliveries.claim_pending(uow, recipient_agent_id="worker", limit=10,
            now=deps.clock.now_iso(), lease_expires_at=iso_plus(deps.clock.now_iso(), 30), max_attempts=5)
        assert not uow.connection.execute("PRAGMA foreign_key_check").fetchall()
    # Reactivation alone must not replay an ambiguous already-written attempt.
    assert client.patch("/api/v1/agents/worker", headers=headers, json={"is_active": True}).status_code == 200
    deps.runtime_dispatcher.scan_once()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.runtime_dispatcher.repo.get(uow, op)["attempt_id"] == row["attempt_id"]
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
    assert len([c for c in peers[0].sent if c.verb == "send_turn"]) == int(uncertain)


def test_prune_and_reactivation_do_not_forget_command_idempotency(runtime):
    deps, client, _, peers, operator, _ = runtime
    headers = {"x-api-key": operator}
    sid = open_rest(runtime).json()["data"]["session_id"]
    args = {"session_id": sid, "payload": {"text": "retained request"}, "idempotency_key": "retain-command"}
    first = tool(client, operator, "harness_send", args)
    assert first["ok"], first
    op = first["data"]["operation_id"]
    wait_operation(runtime, op, lambda row: row["state"] == "SENT_UNCONFIRMED")
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_commands SET created_at='2000-01-01T00:00:00.000000Z' WHERE operation_id=?", (op,))
        before = dict(uow.connection.execute("SELECT * FROM runtime_commands WHERE operation_id=?", (op,)).fetchone())
    assert client.patch("/api/v1/agents/worker", headers=headers, json={"is_active": False}).status_code == 200
    fresh = client.post(f"/api/v1/harness/sessions/{sid}/send", headers=headers,
        json={"payload": {"text": "must not admit"}, "idempotency_key": "inactive-new"})
    assert fresh.status_code == 403, fresh.text
    denied = tool(client, operator, "harness_send", args)
    assert not denied["ok"], denied
    assert tool(client, operator, "harness_get", {"session_id": sid})["ok"]
    response = client.post("/api/v1/admin/prune?dry_run=false", headers=headers)
    assert response.status_code == 200, response.text
    assert client.patch("/api/v1/agents/worker", headers=headers, json={"is_active": True}).status_code == 200
    repeated = tool(client, operator, "harness_send", args)
    assert repeated["ok"] and repeated["data"]["operation_id"] == op, repeated
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert dict(uow.connection.execute("SELECT * FROM runtime_commands WHERE operation_id=?", (op,)).fetchone()) == before
        assert uow.connection.execute("SELECT count(*) FROM runtime_commands").fetchone()[0] == 1
    assert len([c for c in peers[0].sent if c.verb == "send_turn"]) == 1
    assert client.patch("/api/v1/agents/worker", headers=headers, json={"is_active": False}).status_code == 200
    closed = tool(client, operator, "harness_close", {"session_id": sid})
    assert closed["ok"], closed
    wait_close_result(client, operator, closed)
