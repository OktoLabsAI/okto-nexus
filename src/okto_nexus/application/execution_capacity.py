"""Atomic pending admission budgets, charged to immutable operation IDs."""
from ..errors import ErrorCode, OktoNexusError

REGULAR_ACTIONS = ("runtime.open", "turn.submit")
CONTROL_ACTIONS = ("turn.steer", "turn.interrupt", "runtime.close", "approval.decide", "input.provide")
REGULAR_ITEMS = 32
CONTROL_ITEMS = 8
REGULAR_BYTES = REGULAR_ITEMS * 64 * 1024
CONTROL_BYTES = CONTROL_ITEMS * 64 * 1024


def require_admission_capacity(conn, *, server_id, executor_id, action, byte_cost):
    """Called inside the operation's write transaction, before any side effect.

    Accepted children without an outbox row also count. Durable dispatch
    acknowledgement releases pending capacity; an uncertain outcome retains it.
    Replays find their existing operation before calling this function.
    """
    if action in REGULAR_ACTIONS:
        actions, items, budget = REGULAR_ACTIONS, REGULAR_ITEMS, REGULAR_BYTES
    elif action in CONTROL_ACTIONS:
        actions, items, budget = CONTROL_ACTIONS, CONTROL_ITEMS, CONTROL_BYTES
    else:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported execution action.", {})
    if type(byte_cost) is not int or byte_cost < 0:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid operation byte cost.", {})
    rows = conn.execute(
        "SELECT max(admission_bytes,length(CAST(semantic_payload AS BLOB))) AS bytes "
        "FROM execution_operations WHERE server_id=? AND executor_id=? "
        "AND admission_state IN ('ACCEPTED','DISPATCH_PENDING','RECONCILING') "
        "AND action IN (" + ",".join("?" for _ in actions) + ") LIMIT ?",
        (server_id, executor_id, *actions, items),
    ).fetchall()
    if len(rows) >= items or sum(row["bytes"] for row in rows) + byte_cost > budget:
        raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED,
            "The executor pending operation capacity is full. Retry after pending work is acknowledged.",
            {"retry_after_seconds": 1})


def execution_capacity_snapshot(factory):
    """Return fixed-cardinality local gauges, never per-identity metric labels."""
    pending = {lane: {"items": 0, "bytes": 0} for lane in ("regular", "control")}
    dispatch = {lane: {"items": 0, "bytes": 0} for lane in ("regular", "control")}
    with factory.unit_of_work(write=False) as uow:
        for row in uow.connection.execute(
            "SELECT CASE WHEN action IN ('runtime.open','turn.submit') THEN 'regular' "
            "ELSE 'control' END AS lane,COUNT(*) AS items,"
            "SUM(max(admission_bytes,length(CAST(semantic_payload AS BLOB)))) AS bytes "
            "FROM execution_operations "
            "WHERE admission_state IN ('ACCEPTED','DISPATCH_PENDING','RECONCILING') "
            "GROUP BY lane"
        ):
            pending[row["lane"]] = {"items": row["items"], "bytes": row["bytes"]}
        for row in uow.connection.execute(
            "SELECT reservation_class AS lane,COUNT(*) AS items,SUM(reserved_bytes) AS bytes "
            "FROM execution_dispatch_outbox "
            "WHERE dispatch_state IN ('RESERVED','SENDING','RECONCILING') "
            "AND reservation_class IN ('regular','control') GROUP BY reservation_class"
        ):
            dispatch[row["lane"]] = {"items": row["items"], "bytes": row["bytes"]}
    return {
        "status": "available", "pending_totals": pending, "dispatch_totals": dispatch,
        "pending_limits_per_executor": {
            "regular": {"items": REGULAR_ITEMS, "bytes": REGULAR_BYTES},
            "control": {"items": CONTROL_ITEMS, "bytes": CONTROL_BYTES},
        },
    }
