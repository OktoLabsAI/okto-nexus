"""Explicit canonical claim recovery; never replay an uncertain native turn."""
from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_handoff_dispatch import work, claim
from test_runtime_grants import issue
from test_runtime_commands import wait_close_result
from test_runtime_outbox import wait_status
import pytest
from concurrent.futures import ThreadPoolExecutor

runtime = runtime_fixture


def uncertain_work(runtime, *, accepted=False, structured=False, **work_options):
    deps, client, root, _, operator, caller = runtime
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert opened.status_code == 200, opened.text
    hid, worker = work(runtime, **work_options)
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    claimed = (tool(client, caller, "handoff_claim", {"project_root": root, "handoff_id": hid,
        "agent_id": "worker", "runtime_endpoint_id": "endpoint-codex", "execution_grant_id": grant["grant_id"],
        "idempotency_key": "fixture-work", "completion_mode": "structured_result_v1"})
        if structured else claim(runtime, hid, grant, caller))
    assert claimed["ok"], claimed
    op = claimed["data"]["runtime_operation"]["operation_id"]
    row = wait_status(runtime, op, "SENT_UNCONFIRMED")
    if accepted:
        from okto_nexus.domain.harness import HarnessEvent
        session = deps.harness_supervisor.get(row["runtime_session_id"])
        deps.harness_supervisor.event_ingress.capture(HarnessEvent(session_id=session.session_id,
            harness_kind="codex", occurred_at=deps.clock.now_iso(), thread_id="fixture-thread", turn_id="fixture-turn",
            operation_id=op, attempt_id=row["attempt_id"], owner_epoch=row["owner_epoch"], kind="turn_started",
            native_event="fixture/start", payload={}, delivery_phase="started"), connection_id=session.connection_id)
        wait_status(runtime, op, "ACCEPTED")
    wait_close_result(client, operator, tool(client, operator, "harness_close", {
        "session_id": opened.json()["data"]["session_id"]}))
    return hid, worker, claimed["data"]["claim_epoch"], wait_status(runtime, op, "OUTCOME_UNKNOWN")


def recovery(hid, epoch, row, **changes):
    return {"action": "recover_handoff", "operation_id": row["operation_id"],
        "expected_state": row["status"], "expected_attempt_id": row["attempt_id"],
        "expected_owner_epoch": row["owner_epoch"], "expected_handoff_id": hid,
        "expected_claim_epoch": epoch, "idempotency_key": "fixture-work-recovery",
        "reason": "Operator reviewed uncertain work and stopped runtime",
        "acknowledge_duplicate_risk": True, **changes}


def test_operator_reopens_same_handoff_without_releasing_work_as_conversation(runtime):
    deps, client, root, peers, operator, _ = runtime
    hid, worker, epoch, row = uncertain_work(runtime)
    body = recovery(hid, epoch, row)
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=body)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["handoff"]["status"] == "OPEN" and data["inbox_released"] is False
    retry = tool(client, operator, "harness_list", {"view": "outbox", "maintenance": body})
    assert retry["ok"] and retry["data"] == data, retry
    assert sum(c.verb == "send_turn" for p in peers for c in p.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        current = uow.connection.execute("SELECT * FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()
        assert current["status"] == "OPEN" and current["claimed_by"] is None
        assert current["claim_epoch"] == epoch
        attempt = deps.runtime_dispatcher.repo.get(uow, row["operation_id"])
        assert attempt["status"] == row["status"] and attempt["ack_level"] == row["ack_level"]
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
    next_claim = tool(client, worker, "handoff_claim", {"project_root": root, "agent_id": "worker", "handoff_id": hid})
    assert next_claim["ok"] and next_claim["data"]["claim_epoch"] == epoch + 1, next_claim
    stale = tool(client, worker, "handoff_complete", {"project_root": root, "agent_id": "worker",
        "handoff_id": hid, "claim_epoch": epoch, "result": "stale old completion"})
    assert not stale["ok"], stale
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET lease_expires_at='2000-01-01T00:00:00Z' WHERE handoff_id=?", (hid,))
    current = tool(client, worker, "handoff_get", {"project_root": root, "agent_id": "worker", "handoff_id": hid})
    assert current["data"]["status"] == "OPEN", current  # old managed binding cannot pin a new unmanaged claim


@pytest.mark.parametrize("change", [{"expected_claim_epoch": 999}, {"expected_handoff_id": "other-work"},
    {"acknowledge_duplicate_risk": False}, {"expected_attempt_id": "old-attempt"}])
def test_recovery_rejects_stale_work_or_attempt_and_unacknowledged_risk(runtime, change):
    deps, client, _, _, operator, _ = runtime
    hid, _, epoch, row = uncertain_work(runtime)
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(hid, epoch, row, **change))
    assert response.status_code == 409, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == "CLAIMED"
        assert uow.connection.execute("SELECT count(*) FROM runtime_operation_reconciliations").fetchone()[0] == 0


def test_only_operator_can_recover_work_even_with_admission_disabled(runtime):
    deps, client, _, _, operator, caller = runtime
    hid, worker, epoch, row = uncertain_work(runtime)
    args = recovery(hid, epoch, row)
    for key in (caller, worker):
        assert client.post("/api/v1/harness/outbox", headers={"x-api-key": key}, json=args).status_code == 403
        assert tool(client, key, "harness_list", {"view": "outbox", "maintenance": args})["error"]["code"] == "PERMISSION_DENIED"
    deps.config.feature_harness_integrations = False
    result = tool(client, operator, "harness_list", {"view": "outbox", "maintenance": args})
    assert result["ok"] and result["data"]["handoff"]["status"] == "OPEN", result


@pytest.mark.parametrize("status", ["COMPLETED", "VERIFYING", "REJECTED"])
def test_recovery_cannot_reopen_completed_canonical_work(runtime, status):
    deps, client, root, _, operator, _ = runtime
    deps.config.feature_verification = True
    hid, worker, epoch, row = uncertain_work(runtime, **({"acceptance_criteria": ["Review evidence"]} if status == "VERIFYING" else {}))
    completed = tool(client, worker, "handoff_reject" if status == "REJECTED" else "handoff_complete", {
        "project_root": root, "agent_id": "worker", "handoff_id": hid, "claim_epoch": epoch,
        "reason" if status == "REJECTED" else "result": "explicit canonical decision"})
    assert completed["ok"], completed
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(hid, epoch, row))
    assert response.status_code == 409, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == status


def test_work_recovery_and_transport_audit_roll_back_with_canonical_event(runtime, monkeypatch):
    deps, client, _, _, operator, _ = runtime
    hid, _, epoch, row = uncertain_work(runtime)
    original = deps.repos.handoffs.reopen_managed_claim
    def fail_after_transition(*args, **kwargs):
        original(*args, **kwargs)
        from okto_nexus.errors import OktoNexusError, ErrorCode
        raise OktoNexusError(ErrorCode.CONFLICT, "Fixture cut after canonical transition", {})
    monkeypatch.setattr(deps.repos.handoffs, "reopen_managed_claim", fail_after_transition)
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(hid, epoch, row))
    assert response.status_code == 409, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == "CLAIMED"
        assert deps.runtime_dispatcher.repo.get(uow, row["operation_id"])["reconciliation_id"] is None
        assert uow.connection.execute("SELECT count(*) FROM runtime_operation_reconciliations").fetchone()[0] == 0
        assert uow.connection.execute("SELECT count(*) FROM events WHERE type='handoff.recovered'").fetchone()[0] == 0


def test_concurrent_recovery_records_one_canonical_transition_and_audit(runtime):
    deps, client, _, _, operator, _ = runtime
    hid, _, epoch, row = uncertain_work(runtime)
    args = recovery(hid, epoch, row)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=args), range(2)))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json() == results[1].json()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM events WHERE type='handoff.recovered'").fetchone()[0] == 1
        audit = uow.connection.execute("SELECT * FROM runtime_operation_reconciliations").fetchall()
        assert len(audit) == 1
        assert audit[0]["action"] == "abandon_command" and audit[0]["canonical_action"] == "reopen_handoff"
        assert (audit[0]["handoff_id"], audit[0]["claim_epoch"]) == (hid, epoch)
    changed = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(hid, epoch, row, reason="changed decision"))
    assert changed.status_code == 409


def test_late_structured_terminal_cannot_complete_reclaimed_work(runtime):
    import json
    import time
    from okto_nexus.domain.harness import HarnessEvent
    from test_runtime_handoff_dispatch import wait_result
    deps, client, root, _, operator, _ = runtime
    hid, worker, epoch, row = uncertain_work(runtime, accepted=True, structured=True)
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(hid, epoch, row))
    assert response.status_code == 200, response.text
    fresh = tool(client, worker, "handoff_claim", {"project_root": root, "handoff_id": hid, "agent_id": "worker"})
    assert fresh["ok"] and fresh["data"]["claim_epoch"] == epoch + 1, fresh
    with deps.connection_factory.unit_of_work(write=False) as uow:
        connection_id = uow.connection.execute("SELECT connection_id FROM harness_sessions WHERE session_id=?", (row["runtime_session_id"],)).fetchone()[0]
    output = json.dumps({"nexus_work_result": {"schema_version": 1, "operation_id": row["operation_id"],
        "handoff_id": hid, "claim_epoch": epoch, "action": "complete", "result": "late old work"}})
    deps.harness_supervisor.event_ingress.capture(HarnessEvent(session_id=row["runtime_session_id"],
        harness_kind="codex", occurred_at=deps.clock.now_iso(), thread_id="fixture-thread", turn_id="fixture-turn",
        operation_id=row["operation_id"], attempt_id=row["attempt_id"], owner_epoch=row["owner_epoch"],
        kind="turn_completed", native_event="fixture/terminal", payload={}, delivery_phase="terminal",
        delivery_outcome="success", output_text=output, output_snapshot=True), connection_id=connection_id)
    assert wait_result(runtime, row["operation_id"])["output_text"] == output
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            outcome = uow.connection.execute("SELECT state FROM runtime_work_outcomes WHERE operation_id=?", (row["operation_id"],)).fetchone()
        if outcome:
            break
        time.sleep(.01)
    assert outcome and outcome["state"] == "BLOCKED"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        handoff = uow.connection.execute("SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()
        assert (handoff["status"], handoff["claim_epoch"]) == ("CLAIMED", epoch + 1)


def test_terminal_native_turn_can_be_recovered_without_fabricating_handoff_completion(runtime):
    from test_runtime_commands import codex_session
    from test_runtime_handoff_dispatch import wait_result
    deps, client, root, _, operator, caller = runtime
    sid = codex_session(runtime)
    hid, _ = work(runtime)
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    claimed = claim(runtime, hid, grant, caller)
    assert claimed["ok"], claimed
    op = claimed["data"]["runtime_operation"]["operation_id"]
    wait_result(runtime, op)
    wait_close_result(client, operator, tool(client, operator, "harness_close", {"session_id": sid}))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = deps.runtime_dispatcher.repo.get(uow, op)
        assert row["terminal_event_id"]
    response = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(hid, claimed["data"]["claim_epoch"], row))
    assert response.status_code == 200 and response.json()["data"]["handoff"]["status"] == "OPEN", response.text

def test_authenticated_stdio_work_recovery_uses_active_serve_owner(runtime):
    import asyncio
    import json
    import sys
    from test_pr34_remediation import stdio_environment
    deps, client, _, peers, operator, _ = runtime
    hid, _, epoch, row = uncertain_work(runtime)
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
                result = await session.call_tool("harness_list", {"view": "outbox", "maintenance": recovery(hid, epoch, row)})
                result = result.structuredContent or json.loads(result.content[0].text)
                assert result["ok"], result
                return result["data"]
    result = asyncio.run(asyncio.wait_for(recover(), timeout=30))
    retry = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator}, json=recovery(hid, epoch, row))
    assert retry.status_code == 200 and retry.json()["data"] == result, retry.text
    assert sum(c.verb == "send_turn" for peer in peers for c in peer.sent) == 1

