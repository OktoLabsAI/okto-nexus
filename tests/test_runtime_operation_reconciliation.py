"""Operator recovery preserves uncertain transport facts and canonical inbox."""
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_commands import wait_close_result
from test_runtime_outbox import wait_status
from okto_nexus.application.auth import AgentKeyAuthService
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor
import time

runtime = runtime_fixture


def uncertain_delivery(runtime):
    _, client, _, _, operator, _ = runtime
    session = open_rest(runtime).json()["data"]["session_id"]
    sent = send_message(runtime, body="Exactly one logical fixture delivery")
    operation = sent["runtime_operations"][0]
    wait_status(runtime, operation, "SENT_UNCONFIRMED")
    wait_close_result(client, operator, tool(client, operator, "harness_close", {"session_id": session}))
    return sent, wait_status(runtime, operation, "OUTCOME_UNKNOWN")


def recovery(row, **changes):
    return {"action": "release_to_inbox", "operation_id": row["operation_id"],
            "expected_state": row["status"], "expected_attempt_id": row["attempt_id"],
            "expected_owner_epoch": row["owner_epoch"], "idempotency_key": "fixture-takeover",
            "reason": "Operator reviewed isolated uncertain fixture", "acknowledge_duplicate_risk": True, **changes}














def test_timeout_never_allows_takeover_while_original_call_is_running(runtime, monkeypatch):
    deps, client, _, peers, operator, _ = runtime
    open_rest(runtime)
    entered, release = threading.Event(), threading.Event()
    original = peers[0].send
    def stalled(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(peers[0], "send", stalled)
    deps.runtime_dispatcher.send_timeout_seconds = .01
    try:
        sent = send_message(runtime)
        assert entered.wait(5)
        time.sleep(.02)
        deps.runtime_dispatcher._expire_sends()
        row = wait_status(runtime, sent["runtime_operations"][0], "OUTCOME_UNKNOWN")
        result = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(row))
        assert result.status_code == 409 and "in flight" in result.text, result.text
        assert peers[0].sent == []
    finally:
        release.set()






def test_abandoned_command_keeps_history_and_requires_explicit_endpoint_reconciliation(runtime):
    from test_runtime_commands import wait_operation
    deps, client, _, peers, operator, _ = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    args = {"session_id": sid, "payload": {"text": "uncertain original"}, "idempotency_key": "original-command"}
    sent = tool(client, operator, "harness_send", args)
    op = sent["data"]["operation_id"]
    wait_operation(runtime, op, lambda r: r["state"] == "SENT_UNCONFIRMED")
    wait_close_result(client, operator, tool(client, operator, "harness_close", {"session_id": sid}))
    wait_operation(runtime, op, lambda r: r["state"] == "OUTCOME_UNKNOWN")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = dict(uow.connection.execute("SELECT * FROM runtime_commands WHERE operation_id=?", (op,)).fetchone())
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(row, action="abandon_command"))
    assert response.status_code == 200 and not response.json()["data"]["inbox_released"], response.text
    headers = {"x-api-key": operator}
    endpoint = client.get("/api/v1/harness/endpoints", headers=headers).json()["data"]["items"]
    endpoint = next(e for e in endpoint if e["endpoint_id"] == "endpoint-pi")
    assert endpoint["health"] == "quarantined"
    response = client.post("/api/v1/harness/endpoints/endpoint-pi/reconcile", headers=headers, json={
        "expected_revision": endpoint["revision"], "idempotency_key": "endpoint-recovery", "reason": "Fixture reviewed closed runtime",
        "acknowledge_uncertain_effects": True})
    assert response.status_code == 200, response.text
    again = tool(client, operator, "harness_send", args)
    assert again["ok"] and again["data"]["operation_id"] == op, again
    fresh = open_rest(runtime).json()["data"]["session_id"]
    second = tool(client, operator, "harness_send", {"session_id": fresh, "payload": {"text": "explicit fresh turn"}, "idempotency_key": "fresh-command"})
    assert second["ok"], second
    wait_operation(runtime, second["data"]["operation_id"], lambda r: r["state"] == "SENT_UNCONFIRMED")
    assert sum(c.verb == "send_turn" for peer in peers for c in peer.sent) == 2


def test_late_correlated_terminal_is_retained_without_consumption_or_publication(runtime):
    from okto_nexus.domain.harness import HarnessEvent
    from test_runtime_handoff_dispatch import wait_result
    deps, client, _, _, operator, _ = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    op = send_message(runtime)["runtime_operations"][0]
    row = wait_status(runtime, op, "SENT_UNCONFIRMED")
    session = deps.harness_supervisor.get(sid)
    ingress = deps.harness_supervisor.event_ingress
    fields = {"session_id": sid, "harness_kind": "pi", "occurred_at": deps.clock.now_iso(),
        "thread_id": "fixture-thread", "turn_id": "fixture-turn", "operation_id": op,
        "attempt_id": row["attempt_id"], "owner_epoch": row["owner_epoch"]}
    # Native event fixtures enter the real durable ingress, never direct result
    # inserts. The closed peer's buffered terminal arrives after manual takeover.
    ingress.capture(HarnessEvent(**fields, kind="turn_started", native_event="fixture/start", payload={},
        delivery_phase="started"), connection_id=session.connection_id)
    wait_status(runtime, op, "ACCEPTED")
    wait_close_result(client, operator, tool(client, operator, "harness_close", {"session_id": sid}))
    row = wait_status(runtime, op, "OUTCOME_UNKNOWN")
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(row))
    assert response.status_code == 200, response.text
    ingress.capture(HarnessEvent(**fields, kind="turn_completed", native_event="fixture/terminal", payload={},
        delivery_phase="terminal", delivery_outcome="success", output_text="Late fixture output", output_snapshot=True),
        connection_id=session.connection_id)
    result = wait_result(runtime, op)
    assert result["output_text"] == "Late fixture output"
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            result = uow.connection.execute("SELECT * FROM runtime_results WHERE operation_id=?", (op,)).fetchone()
        if result["publication_state"] == "BLOCKED":
            break
        time.sleep(.01)
    assert result["publication_state"] == "BLOCKED"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        delivery = uow.connection.execute("SELECT status,consumer_kind FROM message_deliveries WHERE recipient_agent_id='worker'").fetchone()
        assert delivery["status"] == "unread" and delivery["consumer_kind"] is None
        assert uow.connection.execute("SELECT status FROM delivery_outbox WHERE operation_id=?", (op,)).fetchone()[0] == "OUTCOME_UNKNOWN"
        assert uow.connection.execute("SELECT count(*) FROM messages WHERE subject LIKE 'runtime processing receipt:%'").fetchone()[0] == 0




def test_reconciliation_migration_is_additive_and_repeatable(tmp_path):
    import shutil
    from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
    from test_migrations import make_factory
    old = tmp_path / "schema53"
    old.mkdir()
    for migration in _default_migrations_dir().glob("*.sql"):
        if int(migration.name.split("_", 1)[0]) <= 53:
            shutil.copy(migration, old)
    factory = make_factory(tmp_path)
    MigrationRunner(factory, migrations_dir=old).apply()
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO runtime_access_audit(request_id,action,decision,created_at) VALUES('previous','read','deny','2026-09-23T00:00:00Z')")
    expected = sorted(int(p.name.split('_', 1)[0]) for p in _default_migrations_dir().glob('*.sql') if int(p.name.split('_', 1)[0]) > 53)
    assert MigrationRunner(factory).apply() == expected
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT decision FROM runtime_access_audit WHERE request_id='previous'").fetchone()[0] == "deny"
        for table in ("delivery_outbox", "runtime_commands"):
            assert "reconciliation_id" in {row["name"] for row in uow.connection.execute(f"PRAGMA table_info({table})")}
        assert uow.connection.execute("SELECT count(*) FROM runtime_operation_reconciliations").fetchone()[0] == 0
        assert uow.connection.execute("PRAGMA foreign_key_check").fetchall() == []
