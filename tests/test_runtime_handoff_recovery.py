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
