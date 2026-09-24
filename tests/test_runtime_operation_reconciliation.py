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


def test_explicit_takeover_releases_same_inbox_without_rewriting_transport_or_replaying(runtime):
    deps, client, _, peers, operator, _ = runtime
    sent, row = uncertain_delivery(runtime)
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    with deps.connection_factory.unit_of_work() as uow:
        worker_key = auth.issue_key(uow, agent_id="worker")
    assert tool(client, worker_key, "inbox_pull", {"agent_id": "worker"})["data"]["messages"] == []
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(row))
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["native_replayed"] is False and result["duplicate_risk_acknowledged"] is True
    assert result["transport_state"] == "OUTCOME_UNKNOWN"
    retry = tool(client, operator, "harness_list", {"view": "outbox", "maintenance": recovery(row)})
    assert retry["ok"] and retry["data"] == result, retry
    pulled = tool(client, worker_key, "inbox_pull", {"agent_id": "worker"})
    assert pulled["ok"], pulled
    assert [m["message_id"] for m in pulled["data"]["messages"]] == [sent["message_id"]]
    assert sum(command.verb == "send_turn" for command in peers[0].sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        current = deps.runtime_dispatcher.repo.get(uow, row["operation_id"])
        assert current["status"] == row["status"] and current["ack_level"] == row["ack_level"]
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM runtime_operation_reconciliations").fetchone()[0] == 1


@pytest.mark.parametrize("change", [{"acknowledge_duplicate_risk": False}, {"expected_attempt_id": "stale"},
    {"expected_owner_epoch": 9000}, {"expected_state": "SENDING"}, {"action": "cancel_pending", "acknowledge_duplicate_risk": False}])
def test_uncertain_recovery_rejects_missing_risk_and_stale_snapshot(runtime, change):
    deps, client, _, peers, operator, _ = runtime
    _, row = uncertain_delivery(runtime)
    result = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(row, **change))
    assert result.status_code == 409, result.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT consumer_kind FROM message_deliveries").fetchone()[0] == "push"
        assert uow.connection.execute("SELECT count(*) FROM runtime_operation_reconciliations").fetchone()[0] == 0
    assert sum(c.verb == "send_turn" for c in peers[0].sent) == 1


def test_recovery_has_operator_parity_and_survives_admission_flag_off(runtime):
    deps, client, _, _, operator, caller = runtime
    _, row = uncertain_delivery(runtime)
    body = recovery(row)
    assert client.post("/api/v1/harness/outbox", headers={"x-api-key": caller}, json=body).status_code == 403
    assert tool(client, caller, "harness_list", {"view": "outbox", "maintenance": body})["error"]["code"] == "PERMISSION_DENIED"
    assert client.get("/api/v1/harness/outbox", headers={"x-api-key": caller}).status_code == 403
    deps.config.feature_harness_integrations = False
    result = tool(client, operator, "harness_list", {"view": "outbox", "maintenance": body})
    assert result["ok"], result
    inspected = client.get("/api/v1/harness/outbox", headers={"x-api-key": operator}, params={"operation_id": row["operation_id"]})
    assert inspected.status_code == 200, inspected.text
    item = inspected.json()["data"]["items"][0]
    assert item["state"] == "OUTCOME_UNKNOWN" and item["reconciliation"]["action"] == "release_to_inbox"
    assert not any(key in item for key in ("envelope", "credential_binding", "context", "payload"))


def test_concurrent_recovery_is_one_atomic_decision_and_conflicting_key_fails(runtime):
    deps, client, _, _, operator, _ = runtime
    _, row = uncertain_delivery(runtime)
    body = recovery(row)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=body), range(2)))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json() == results[1].json()
    changed = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(row, reason="Different decision"))
    assert changed.status_code == 409
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_operation_reconciliations").fetchone()[0] == 1


def test_recovery_rolls_back_audit_and_source_when_inbox_release_fails(runtime, monkeypatch):
    deps, client, _, _, operator, _ = runtime
    _, row = uncertain_delivery(runtime)
    original = deps.repos.deliveries.release_runtime_reservation
    def cut(*args, **kwargs):
        original(*args, **kwargs)
        from okto_nexus.errors import OktoNexusError, ErrorCode
        raise OktoNexusError(ErrorCode.CONFLICT, "Fixture transactional cut", {})
    monkeypatch.setattr(deps.repos.deliveries, "release_runtime_reservation", cut)
    result = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(row))
    assert result.status_code == 409
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT consumer_kind FROM message_deliveries").fetchone()[0] == "push"
        assert uow.connection.execute("SELECT reconciliation_id FROM delivery_outbox").fetchone()[0] is None
        assert uow.connection.execute("SELECT count(*) FROM runtime_operation_reconciliations").fetchone()[0] == 0


def test_pending_cancel_is_safe_before_send_intent(runtime, monkeypatch):
    deps, client, _, peers, operator, _ = runtime
    open_rest(runtime)
    entered, release = threading.Event(), threading.Event()
    original = deps.runtime_dispatcher._execute
    def before_send(operation, attempt):
        entered.set()
        assert release.wait(10)
        return original(operation, attempt)
    monkeypatch.setattr(deps.runtime_dispatcher, "_execute", before_send)
    try:
        sent = send_message(runtime)
        assert entered.wait(5)
        row = wait_status(runtime, sent["runtime_operations"][0], "CLAIMED")
        result = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(row,
            action="cancel_pending", acknowledge_duplicate_risk=False))
        assert result.status_code == 200, result.text
    finally:
        release.set()
    wait_status(runtime, row["operation_id"], "CANCELLED")
    assert peers[0].sent == []


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


def test_active_runtime_cannot_be_released_just_by_acknowledging_risk(runtime):
    _, client, _, _, operator, _ = runtime
    open_rest(runtime)
    sent = send_message(runtime)
    row = wait_status(runtime, sent["runtime_operations"][0], "SENT_UNCONFIRMED")
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(row))
    assert response.status_code == 409 and "runtime before takeover" in response.text, response.text


def test_managed_handoff_cannot_be_released_as_conversation(runtime):
    from test_runtime_handoff_dispatch import work, claim
    from test_runtime_grants import issue
    deps, client, root, _, operator, caller = runtime
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    sid = opened.json()["data"]["session_id"]
    hid, _ = work(runtime)
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    admitted = claim(runtime, hid, grant, caller)
    assert admitted["ok"], admitted
    op = admitted["data"]["runtime_operation"]["operation_id"]
    wait_status(runtime, op, "SENT_UNCONFIRMED")
    wait_close_result(client, operator, tool(client, operator, "harness_close", {"session_id": sid}))
    row = wait_status(runtime, op, "OUTCOME_UNKNOWN")
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(row))
    assert response.status_code == 409 and "handoff recovery" in response.text, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == "CLAIMED"


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


def test_authenticated_stdio_recovery_uses_active_serve_owner(runtime):
    import asyncio
    import json
    import sys
    from test_pr34_remediation import stdio_environment
    deps, client, _, peers, operator, _ = runtime
    _, row = uncertain_delivery(runtime)
    async def recover():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        env = stdio_environment(runtime)
        env["OKTO_NEXUS_API_KEY"] = operator  # Disposable Nexus operator, never a native peer.
        params = StdioServerParameters(command=sys.executable, args=["-m", "okto_nexus.adapters.inbound.mcp.server",
            "--home", str(deps.config.home_dir), "--feature-harness-integrations", "true"], env=env)
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool("harness_list", {"view": "outbox", "maintenance": recovery(row)})
                result = result.structuredContent or json.loads(result.content[0].text)
                assert result["ok"], result
                return result["data"]
    result = asyncio.run(asyncio.wait_for(recover(), timeout=30))
    retry = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(row))
    assert retry.status_code == 200 and retry.json()["data"] == result, retry.text
    assert sum(c.verb == "send_turn" for peer in peers for c in peer.sent) == 1


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
    assert MigrationRunner(factory).apply() == [54, 55, 56, 57, 58]
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT decision FROM runtime_access_audit WHERE request_id='previous'").fetchone()[0] == "deny"
        for table in ("delivery_outbox", "runtime_commands"):
            assert "reconciliation_id" in {row["name"] for row in uow.connection.execute(f"PRAGMA table_info({table})")}
        assert uow.connection.execute("SELECT count(*) FROM runtime_operation_reconciliations").fetchone()[0] == 0
        assert uow.connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_restart_with_admission_disabled_can_recover_existing_operations(runtime):
    from fastapi.testclient import TestClient
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.adapters.inbound.http.app import build_app
    deps, _, _, peers, operator, _ = runtime
    _, row = uncertain_delivery(runtime)
    from okto_nexus.application.runtime_shutdown import shutdown_runtime
    assert shutdown_runtime(deps.runtime_dispatcher, deps.harness_supervisor)["state"] == "drained"
    recovered = bootstrap({}, ["--home", str(deps.config.home_dir), "--feature-harness-integrations", "false"])
    constructed = []
    def forbidden_native(**kwargs):
        constructed.append(True)
        raise AssertionError("Recovery-only serve cannot construct a native peer")
    recovered.harness_connector_factories = {kind: forbidden_native for kind in ("pi", "codex", "claude_code")}
    with TestClient(build_app(recovered)) as client:
        headers = {"x-api-key": operator}
        inspected = client.get("/api/v1/harness/outbox", headers=headers, params={"operation_id": row["operation_id"]})
        assert inspected.status_code == 200, inspected.text
        result = client.post("/api/v1/harness/outbox", headers=headers, json=recovery(row))
        assert result.status_code == 200, result.text
        assert result.json()["data"]["native_replayed"] is False
    assert constructed == []
    assert sum(c.verb == "send_turn" for peer in peers for c in peer.sent) == 1
