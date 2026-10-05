"""Dispatch quota selection over real SQLite, with synthetic backlog rows."""
import pytest

from test_dispatch_pump import owner
from okto_nexus.application.execution_dispatch import reserve_execution_dispatch


def backlog(state, action, count, *, payload=None):
    factory, channel = state[0].connection_factory, state[5]
    with factory.unit_of_work() as uow:
        source = dict(uow.connection.execute(
            "SELECT * FROM execution_operations WHERE operation_id=?",
            (state[6]["operation_id"],)).fetchone())
        for index in range(count):
            row = dict(source, operation_id=f"backlog-{action}-{index:04d}", action=action)
            if payload is not None:
                row["semantic_payload"] = payload
            uow.connection.execute(
                "INSERT INTO execution_operations (" + ",".join(row) + ") VALUES (" +
                ",".join("?" for _ in row) + ")", tuple(row.values()))
            uow.connection.execute(
                "INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state) "
                "VALUES(?,?,?,'PENDING')",
                (channel.server_id, channel.executor_id, row["operation_id"]))


def reserve(state, **limits):
    channel = state[5]
    return reserve_execution_dispatch(state[0].connection_factory,
        server_id=channel.server_id, executor_id=channel.executor_id,
        remote_ready=True, channel=channel, **limits)


@pytest.mark.parametrize("constraint", ["items", "bytes", "oversized"])
def test_blocked_control_backlog_does_not_hide_eligible_productive_work(owner, constraint):
    # More than the old 32-row selection window remains ahead of the opening.
    backlog(owner, "turn.interrupt", 40,
            payload='"' + ("x" * 2048) + '"' if constraint == "oversized" else None)
    limits = {}
    if constraint == "oversized":
        limits["control_bytes"] = 1024
    else:
        first = reserve(owner)
        assert first.reservation_class == "control"
        if constraint == "items":
            limits["control_items"] = 1
        else:
            limits["control_bytes"] = first.reserved_bytes
    productive = reserve(owner, **limits)
    assert productive is not None
    assert productive.operation_id == owner[6]["operation_id"]
    assert productive.reservation_class == "regular"
    with owner[0].connection_factory.unit_of_work(write=False) as uow:
        retained = uow.connection.execute(
            "SELECT COUNT(*) FROM execution_dispatch_outbox WHERE dispatch_state='PENDING'").fetchone()[0]
    assert retained >= 39, "Ineligible controls must remain durable, never be dropped"


@pytest.mark.parametrize("constraint", ["items", "bytes"])
def test_uncertain_send_keeps_exact_capacity_until_reconciled(owner, constraint):
    original = reserve(owner)
    assert original.operation_id == owner[6]["operation_id"]
    with owner[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE execution_dispatch_outbox SET dispatch_state='RECONCILING' WHERE operation_id=?",
            (original.operation_id,))
        uow.connection.execute(
            "UPDATE execution_operations SET admission_state='RECONCILING' WHERE operation_id=?",
            (original.operation_id,))
    backlog(owner, "turn.submit", 1)
    with owner[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE execution_operations SET admission_state='ACCEPTED' WHERE action='turn.submit'")
    limits = {"regular_items": 1} if constraint == "items" else {"regular_bytes": original.reserved_bytes}
    assert reserve(owner, **limits) is None
    # Only a durable resolution returns that exact held capacity.
    with owner[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE execution_dispatch_outbox SET dispatch_state='RESOLVED_TERMINAL',"
            "reserved_bytes=0,reservation_class=NULL WHERE operation_id=?", (original.operation_id,))
    following = reserve(owner, **limits)
    assert following is not None and following.operation_id != original.operation_id


def test_fitting_control_after_oversized_rows_uses_exact_utf8_cost(owner):
    backlog(owner, "turn.interrupt", 40, payload='"' + ("x" * 2048) + '"')
    payload = '"é"'
    backlog(owner, "runtime.close", 1, payload=payload)
    held = reserve(owner, control_bytes=len(payload.encode("utf-8")))
    assert held is not None and held.operation_id == "backlog-runtime.close-0000"
    assert held.reserved_bytes == 4 and held.reservation_class == "control"
