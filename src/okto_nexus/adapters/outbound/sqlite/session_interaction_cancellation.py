"""Cancel one owned, unsent session input while preserving its FIFO history."""

from collections.abc import Callable

from ....domain.session_interaction import (
    MAX_SQLITE_INTEGER,
    InputAuthor,
    InputDeliveryState,
    InputScope,
    QueuedReceipt,
    may_cancel,
)
from ....errors import ErrorCode, OktoNexusError
from .connection import SqliteUnitOfWork
from .session_interaction import _conflict, _scope_params


def cancel_input(
    uow: SqliteUnitOfWork,
    *,
    scope: InputScope,
    author: InputAuthor,
    input_id: str,
    capability_revision: str,
    expected_queue_revision: int,
    expected_input_revision: int,
    verify_authority: Callable[[], str],
) -> QueuedReceipt:
    """Commit only a local cancellation under the caller's authority fence.

    The verifier must prove current cancellation authority for this exact
    author and scope and return the current capability revision. Acquire that
    authority fence before the execution writer and return the receipt after
    commit. Cancelling does not require or consume a productive runtime grant.
    Leave any PREPARED attempt for capacity reconciliation. The CANCELLED row
    prevents its reconciler from admitting a turn.
    """
    uow.require_active_writer()
    if verify_authority() != capability_revision or not capability_revision:
        raise _conflict("INPUT_CAPABILITY_CHANGED", "The input cancellation capability changed.")

    conn = uow.connection
    params = {**_scope_params(scope), "input_id": input_id, "authority_ref": author.authority_ref,
              "surface": author.surface, "queue_revision": expected_queue_revision,
              "input_revision": expected_input_revision}
    row = conn.execute("""
        SELECT i.status, i.operation_id, i.possible_effect, i.input_revision, i.enqueue_sequence,
            q.revision AS queue_revision
        FROM session_interaction_inputs i
        JOIN session_interaction_queues q USING (server_id, executor_id, session_id)
        JOIN execution_sessions s USING (server_id, executor_id, session_id)
        JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id AND b.binding_id=s.binding_id
        JOIN execution_workspace_bindings w ON w.server_id=s.server_id AND w.executor_id=s.executor_id
            AND w.workspace_binding_id=s.workspace_binding_id AND w.workspace_id=s.workspace_id
        JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id
        WHERE i.server_id=:server_id AND i.executor_id=:executor_id AND i.session_id=:session_id
          AND i.input_id=:input_id AND i.authority_ref=:authority_ref AND i.surface=:surface
          AND i.owner_generation=:owner_generation AND i.binding_id=:binding_id AND i.workspace_id=:workspace_id
          AND i.workspace_binding_id=:workspace_binding_id AND i.agent_id=:agent_id
          AND s.owner_generation=i.owner_generation AND s.binding_id=i.binding_id
          AND s.workspace_id=i.workspace_id AND s.workspace_binding_id=i.workspace_binding_id
          AND b.workspace_binding_id=i.workspace_binding_id AND e.agent_id=i.agent_id AND e.workspace_id=i.workspace_id
    """, params).fetchone()
    if row is None:
        raise OktoNexusError(ErrorCode.NOT_FOUND, "The input is unavailable in this author and session scope.", {})
    if not may_cancel(InputDeliveryState(row["status"])) or row["operation_id"] is not None or row["possible_effect"]:
        raise _conflict("INPUT_NOT_CANCELLABLE", "This input can no longer be cancelled from the queue.")
    if (row["queue_revision"], row["input_revision"]) != (expected_queue_revision, expected_input_revision):
        raise _conflict("INPUT_REVISION_CHANGED", "The queue or input changed. Review it before cancelling.")
    if MAX_SQLITE_INTEGER in (expected_queue_revision, expected_input_revision):
        raise _conflict("INPUT_REVISION_LIMIT", "The queue or input revision limit was reached.")

    # The writer serializes the comparison with both dispatch and cancellation.
    conn.execute("""
        UPDATE session_interaction_inputs SET status='CANCELLED', input_revision=input_revision+1
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id AND input_id=:input_id
          AND input_revision=:input_revision
    """, params)
    conn.execute("""
        UPDATE session_interaction_queues SET revision=revision+1
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id AND revision=:queue_revision
    """, params)
    return QueuedReceipt(input_id, row["enqueue_sequence"], expected_input_revision + 1,
                         expected_queue_revision + 1, InputDeliveryState.CANCELLED, None, False)
