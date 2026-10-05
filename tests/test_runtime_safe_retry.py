"""Retry only an observed transient pre-write failure, on the same logical intent."""
import time
import pytest

from okto_nexus.domain.base import iso_plus, iso_to_epoch
from test_pr34_remediation import runtime as runtime_fixture, open_rest, send_message, tool
from test_runtime_outbox import operation, wait_status
from test_runtime_operation_reconciliation import recovery

runtime = runtime_fixture


def busy_lane(runtime, monkeypatch):
    deps, _, _, peers, _, _ = runtime
    session = open_rest(runtime).json()["data"]["session_id"]
    peer = peers[0]
    peer.delivery_event_phase = lambda event: {"turn_started": "started", "turn_completed": "terminal"}.get(event.kind)
    # A trusted legacy/internal turn is active in the adapter, but has no
    # canonical outbox operation. This exercises the real adapter's final fence.
    deps.harness_supervisor.send(session, "send_turn", {"text": "existing internal turn"})
    peer.push_event(kind="turn_started")
    clock = [deps.clock.now_iso()]
    monkeypatch.setattr(deps.clock, "now_iso", lambda: clock[0])
    return peer, clock


def test_busy_before_native_write_waits_for_deadline_and_preserves_logical_operation(runtime, monkeypatch):
    deps = runtime[0]
    peer, clock = busy_lane(runtime, monkeypatch)
    deps.runtime_dispatcher.retry_jitter = lambda: 1
    sent = send_message(runtime, body="only once after safe retry")
    operation_id = sent["runtime_operations"][0]
    first = wait_status(runtime, operation_id, "RETRY_WAIT")
    assert first["ack_level"] == "NONE" and first["next_attempt_at"] > clock[0]
    assert iso_to_epoch(first["next_attempt_at"]) - iso_to_epoch(clock[0]) == 1.25
    for _ in range(5):
        deps.runtime_dispatcher.scan_once()
    assert operation(runtime, operation_id)["attempt_count"] == 1
    assert sum(command.verb == "send_turn" for command in peer.sent) == 1
    peer.push_event(kind="turn_completed")
    # Event capture/projection is asynchronous. Wait only for the real adapter
    # to consume its native terminal, without changing its internal attempt map.
    deadline = time.monotonic() + 5
    while not peer._queue.empty() and time.monotonic() < deadline:
        time.sleep(.01)
    clock[0] = first["next_attempt_at"]
    deps.runtime_dispatcher.wake()
    second = wait_status(runtime, operation_id, "SENT_UNCONFIRMED")
    assert second["attempt_count"] == 2 and second["attempt_id"] != first["attempt_id"]
    assert second["message_id"] == sent["message_id"] and second["request_hash"] == first["request_hash"]
    assert sum(command.verb == "send_turn" for command in peer.sent) == 2
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM message_deliveries").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(DISTINCT attempt_id) FROM runtime_delivery_attempt_events WHERE operation_id=?",
            (operation_id,)).fetchone()[0] == 2
        proof = uow.connection.execute("SELECT next_attempt_at,retry_basis FROM runtime_delivery_attempt_events "
            "WHERE operation_id=? AND state='RETRY_WAIT'", (operation_id,)).fetchone()
        assert tuple(proof) == (first["next_attempt_at"], "LANE_BUSY_BEFORE_WRITE")


def test_safe_retry_exhaustion_is_bounded_and_can_be_released_to_pull(runtime, monkeypatch):
    deps, client, _, _, operator, _ = runtime
    peer, clock = busy_lane(runtime, monkeypatch)
    deps.runtime_dispatcher.retry_jitter = lambda: 0
    operation_id = send_message(runtime)["runtime_operations"][0]
    first = wait_status(runtime, operation_id, "RETRY_WAIT")
    clock[0] = first["next_attempt_at"]
    deps.runtime_dispatcher.wake()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        second = operation(runtime, operation_id)
        if second["status"] == "RETRY_WAIT" and second["attempt_count"] == 2:
            break
        time.sleep(.01)
    assert second["attempt_count"] == 2 and second["status"] == "RETRY_WAIT"
    assert iso_to_epoch(second["next_attempt_at"]) - iso_to_epoch(clock[0]) == 2
    clock[0] = second["next_attempt_at"]
    deps.runtime_dispatcher.wake()
    exhausted = wait_status(runtime, operation_id, "REJECTED")
    assert exhausted["attempt_count"] == 3 and exhausted["next_attempt_at"] is None
    assert sum(command.verb == "send_turn" for command in peer.sent) == 1
    released = client.post("/api/v1/harness/outbox", headers={"x-api-key": operator},
        json=recovery(exhausted, acknowledge_duplicate_risk=False))
    assert released.status_code == 200, released.text
    assert released.json()["data"]["inbox_released"]


def test_retry_wait_can_be_cancelled_without_sending_at_its_deadline(runtime, monkeypatch):
    deps, client, _, _, operator, _ = runtime
    peer, clock = busy_lane(runtime, monkeypatch)
    operation_id = send_message(runtime)["runtime_operations"][0]
    row = wait_status(runtime, operation_id, "RETRY_WAIT")
    cancelled = tool(client, operator, "harness_list", {"view": "outbox", "maintenance": recovery(row,
        action="cancel_pending", acknowledge_duplicate_risk=False)})
    assert cancelled["ok"], cancelled
    clock[0] = row["next_attempt_at"]
    deps.runtime_dispatcher.scan_once()
    assert operation(runtime, operation_id)["status"] == "CANCELLED"
    assert sum(command.verb == "send_turn" for command in peer.sent) == 1


def test_new_turns_cannot_overtake_a_retry_wait_on_the_same_lane(runtime, monkeypatch):
    deps, client, _, _, operator, _ = runtime
    peer, clock = busy_lane(runtime, monkeypatch)
    first_id = send_message(runtime)["runtime_operations"][0]
    wait_status(runtime, first_id, "RETRY_WAIT")
    clock[0] = iso_plus(clock[0], .001)
    second_id = send_message(runtime)["runtime_operations"][0]
    direct = tool(client, operator, "harness_send", {"session_id": peer.session.session_id,
        "payload": {"text": "later administrative turn"}})
    assert direct["ok"], direct
    deps.runtime_dispatcher.scan_once()
    deps.runtime_dispatcher.command_dispatcher.scan_once()
    assert operation(runtime, second_id)["status"] == "PENDING"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        command = deps.runtime_dispatcher.command_dispatcher.repo.get(uow, direct["data"]["operation_id"])
        assert command["status"] == "PENDING"
    assert sum(command.verb == "send_turn" for command in peer.sent) == 1


def test_retry_revalidates_actor_authority_before_any_new_native_call(runtime, monkeypatch):
    deps = runtime[0]
    peer, clock = busy_lane(runtime, monkeypatch)
    operation_id = send_message(runtime)["runtime_operations"][0]
    row = wait_status(runtime, operation_id, "RETRY_WAIT")
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='caller'")
    clock[0] = row["next_attempt_at"]
    deps.runtime_dispatcher.wake()
    rejected = wait_status(runtime, operation_id, "REJECTED")
    assert rejected["reason"] == "authorization_changed"
    assert sum(command.verb == "send_turn" for command in peer.sent) == 1


def test_persisted_deadline_wakes_retry_without_an_external_signal(runtime, monkeypatch):
    deps = runtime[0]
    real_clock = deps.clock.now_iso
    peer, _ = busy_lane(runtime, monkeypatch)
    deps.runtime_dispatcher.retry_jitter = lambda: 0
    deps.runtime_dispatcher.recovery_seconds = 3600
    operation_id = send_message(runtime)["runtime_operations"][0]
    first = wait_status(runtime, operation_id, "RETRY_WAIT")
    monkeypatch.setattr(deps.clock, "now_iso", real_clock)
    # No wake/scan or native event after this point. Only the durable deadline
    # can select a second attempt before the one-hour recovery scan interval.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = operation(runtime, operation_id)
        if current["attempt_count"] >= 2:
            break
        time.sleep(.01)
    assert current["attempt_count"] >= 2 and current["attempt_id"] != first["attempt_id"]
    assert sum(command.verb == "send_turn" for command in peer.sent) == 1


def test_new_dispatch_owner_preserves_retry_deadline_without_early_replay(runtime, monkeypatch):
    from test_runtime_outbox import restart_dispatcher
    deps = runtime[0]
    peer, _ = busy_lane(runtime, monkeypatch)
    operation_id = send_message(runtime)["runtime_operations"][0]
    first = wait_status(runtime, operation_id, "RETRY_WAIT")
    old = deps.runtime_dispatcher
    old.quiesce()
    old.close()
    new = restart_dispatcher(runtime, old)
    new.scan_once()
    current = operation(runtime, operation_id)
    assert current["status"] == "RETRY_WAIT"
    assert current["next_attempt_at"] == first["next_attempt_at"]
    assert current["attempt_count"] == 1 and current["attempt_id"] == first["attempt_id"]
    assert sum(command.verb == "send_turn" for command in peer.sent) == 1


@pytest.mark.parametrize("field,value", [("ack_level", "TRANSPORT_WRITE"), ("retry_basis", None), ("reason", "unknown")])
def test_retry_wait_label_alone_does_not_authorize_safe_cancellation(runtime, monkeypatch, field, value):
    deps, client, _, _, operator, _ = runtime
    _, _clock = busy_lane(runtime, monkeypatch)
    operation_id = send_message(runtime)["runtime_operations"][0]
    row = wait_status(runtime, operation_id, "RETRY_WAIT")
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute(f"UPDATE delivery_outbox SET {field}=? WHERE operation_id=?", (value, operation_id))
    result = tool(client, operator, "harness_list", {"view": "outbox", "maintenance": recovery(row,
        action="cancel_pending", acknowledge_duplicate_risk=False)})
    assert not result["ok"] and result["error"]["code"] == "CONFLICT", result


def test_lost_non_delivery_proof_commit_never_enables_replay(runtime, monkeypatch):
    from test_runtime_outbox import restart_dispatcher
    deps = runtime[0]
    peer, _ = busy_lane(runtime, monkeypatch)
    owner = deps.runtime_dispatcher
    persist = owner.repo.retry_not_sent

    def commit_cut(*args, **kwargs):
        persist(*args, **kwargs)
        raise OSError("Isolated proof commit cut")

    monkeypatch.setattr(owner.repo, "retry_not_sent", commit_cut)
    operation_id = send_message(runtime)["runtime_operations"][0]
    wait_status(runtime, operation_id, "SENDING")
    deadline = time.monotonic() + 5
    while owner.operation_inflight(operation_id) and time.monotonic() < deadline:
        time.sleep(.01)
    assert not owner.operation_inflight(operation_id)
    assert all(worker.is_alive() for worker in owner._threads)
    assert operation(runtime, operation_id)["next_attempt_at"] is None
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM runtime_delivery_attempt_events "
            "WHERE operation_id=? AND state='RETRY_WAIT'", (operation_id,)).fetchone()
    owner.quiesce()
    owner.close()
    new = restart_dispatcher(runtime, owner)
    new.scan_once()
    assert operation(runtime, operation_id)["status"] == "OUTCOME_UNKNOWN"
    assert sum(command.verb == "send_turn" for command in peer.sent) == 1
