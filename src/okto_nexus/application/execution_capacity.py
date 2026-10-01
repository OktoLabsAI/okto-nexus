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
