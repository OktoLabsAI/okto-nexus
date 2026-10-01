"""Governed handoff claims retain their identity through canonical execution."""
import json
from pathlib import Path
import time

import pytest
from nexus_connector_core import RuntimeEvent
from okto_nexus.domain.base import iso_plus
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local


def prepare(setup, binding, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    deps, _, client, headers, *_, root = setup
    client.headers["host"] = "127.0.0.1:8000"
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='none' WHERE endpoint_id=?", (binding["endpoint_id"],))
    def call(name, actor="subject", **kwargs):
        return tool(client, headers[actor]["Authorization"].removeprefix("Bearer "), name,
                    dict(project_root=str(root), **kwargs))
    created = call("handoff_create", actor="operator", from_agent_id="operator", visibility="eligible",
                   target=dict(strategy="direct", agent_id="subject"), payload="Perform this governed review.")
    assert created["ok"], created
    handoff = created["data"]["handoff_id"]
    response = client.post("/api/v1/harness/grants", headers=headers["operator"], json=dict(
        actor_agent_id="subject", endpoint_id=binding["endpoint_id"], actions=["execute_work"],
        max_executions=1, expires_at=iso_plus(deps.clock.now_iso(), 600)))
    assert response.status_code == 200, response.text
    grant = response.json()["data"]["grant_id"]
    def claim(**extra):
        return call("handoff_claim", handoff_id=handoff, agent_id="subject", runtime_endpoint_id=binding["endpoint_id"],
                    execution_grant_id=grant, idempotency_key="canonical-work", **extra)
    return handoff, grant, claim, call


def test_managed_claim_replays_and_native_terminal_does_not_complete(connected_local, monkeypatch):
    setup, binding, native = connected_local
    handoff, grant, claim, call = prepare(setup, binding, monkeypatch)
    first = claim()
    assert first["ok"], first
    repeated = claim()
    assert repeated["ok"], repeated
    assert first["data"]["runtime_operation"]["operation_id"] == repeated["data"]["runtime_operation"]["operation_id"]
    deps, _, client, *_ = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant,)).fetchone()[0] == 1
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_handoff_bindings").fetchone()[0] == 1
        envelope = json.loads(uow.connection.execute("SELECT envelope FROM delivery_outbox").fetchone()[0])
        assert envelope["handoff_id"] == handoff and envelope["claim_epoch"] == 1
    wait_receipt(setup, turn)
    assert native.opens == 1 and len(native.native.sent) == 1
    viewed = call("handoff_get", handoff_id=handoff, agent_id="subject")
    assert viewed["ok"], viewed
    assert {op["session_id"] for op in viewed["data"]["runtime_execution"]["canonical_operations"]} == {turn["session_id"]}
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute("SELECT * FROM execution_local_streams").fetchone())
    client.portal.call(native.native.queue.put, RuntimeEvent(stream["server_id"], stream["executor_id"],
        stream["session_id"], stream["stream_epoch"], 0, "turn_state", "technical.complete",
        {"delivery_phase": "terminal", "delivery_outcome": "success"}, operation_id=turn["operation_id"]))
    wait_receipt(setup, turn, stages=("SUCCEEDED",))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status,result FROM handoffs WHERE handoff_id=?", (handoff,)).fetchone()[:] == ("CLAIMED", None)
    completed = call("handoff_complete", handoff_id=handoff, agent_id="subject", claim_epoch=1, result="Reviewed through the governed completion call.")
    assert completed["ok"], completed
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (handoff,)).fetchone()[0] == "COMPLETED"
    closed = admit(setup, binding, "work-close", "runtime.close", session_id=turn["session_id"])
    wait_receipt(setup, closed, stages=("SUCCEEDED",))


@pytest.mark.parametrize("change", ["grant", "claim_epoch"])
def test_work_authority_change_after_claim_blocks_core(connected_local, monkeypatch, change):
    setup, binding, native = connected_local
    handoff, grant, claim, _ = prepare(setup, binding, monkeypatch)
    deps, app, client, *_ = setup
    lock = app.state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        result = claim()
        assert result["ok"], result
        with deps.connection_factory.unit_of_work() as uow:
            if change == "grant":
                uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at=? WHERE grant_id=?", (deps.clock.now_iso(), grant))
            else:
                uow.connection.execute("UPDATE handoffs SET claim_epoch=claim_epoch+1 WHERE handoff_id=?", (handoff,))
    finally:
        client.portal.call(lock.release)
    until = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT dispatch_state,last_error FROM execution_dispatch_outbox").fetchone()
        if row[0] == "RESOLVED_TERMINAL":
            assert "PERMISSION_DENIED" in row[1]
            break
        assert time.monotonic() < until, tuple(row)
        time.sleep(.02)
    assert native.opens == 0


@pytest.mark.parametrize("denial", ["readiness", "structured_result"])
def test_rejected_execution_rolls_back_claim_and_work_budget(connected_local, monkeypatch, denial):
    from okto_nexus.bootstrap import execution_compat
    setup, binding, native = connected_local
    handoff, grant, claim, _ = prepare(setup, binding, monkeypatch)
    if denial == "readiness":
        info = execution_compat.protocol_info()
        monkeypatch.setattr(execution_compat, "protocol_info", lambda: {**info, "remote_execution_ready": False})
    result = claim(**({"completion_mode": "structured_result_v1"} if denial == "structured_result" else {}))
    assert not result["ok"], result
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status,claimed_by FROM handoffs WHERE handoff_id=?", (handoff,)).fetchone()[:] == ("OPEN", None)
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant,)).fetchone()[0] == 0
        for table in ("runtime_handoff_bindings", "delivery_outbox", "execution_operations", "execution_domain_deliveries"):
            assert uow.connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
    assert native.opens == 0
