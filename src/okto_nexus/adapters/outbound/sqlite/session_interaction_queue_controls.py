"""Durable queue pause on the canonical session, independent of input state."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from sqlite3 import Connection

from ....domain.execution.keys import SessionKey
from ....domain.session_interaction import MAX_SQLITE_INTEGER, InputScope
from .connection import SqliteUnitOfWork
from .session_interaction_interrupt_targets import interrupt_target_status


@dataclass(frozen=True, slots=True)
class QueuePauseReceipt:
    queue_revision: int
    paused_owner_generation: int | None

    @property
    def paused(self) -> bool:
        return self.paused_owner_generation is not None


def is_input_queue_paused(conn: Connection, session: SessionKey) -> bool:
    """The barrier applies to this stable session key across owner generations."""
    return conn.execute("""
        SELECT 1 FROM session_interaction_queues
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND paused_owner_generation IS NOT NULL
    """, asdict(session)).fetchone() is not None


def has_unresolved_interrupt(conn: Connection, session: SessionKey) -> bool:
    key = asdict(session)
    pending = conn.execute("""
        SELECT o.admission_state,o.binding_id,o.workspace_id,o.workspace_binding_id,o.subject_agent_id AS agent_id,
            c.owner_generation AS session_owner_generation,c.native_turn_id,t.target_operation_id,t.target_stream_epoch,
            r.stage AS control_stage
        FROM execution_operations o
        LEFT JOIN session_interaction_controls c USING (server_id,executor_id,operation_id)
        LEFT JOIN session_interaction_interrupt_targets t USING (server_id,executor_id,operation_id)
        LEFT JOIN execution_dispatch_outbox d USING (server_id,executor_id,operation_id)
        LEFT JOIN execution_receipts r ON r.server_id=o.server_id AND r.executor_id=o.executor_id
          AND r.operation_id=o.operation_id AND r.receipt_revision=d.last_receipt_revision
        WHERE o.server_id=:server_id AND o.executor_id=:executor_id AND o.session_id=:session_id
          AND o.action='turn.interrupt' AND o.admission_state NOT IN ('REJECTED','RESOLVED_TERMINAL')
    """, key)
    for row in pending:
        # Core acknowledges delivery of the control. The original turn's
        # authenticated terminal fact, when correlated, settles the barrier.
        if (row['admission_state'] != 'DISPATCHED' or row['control_stage'] not in ('SUBMITTED', 'ACCEPTED')
                or interrupt_target_status(conn, {**key, **dict(row)}, row) == 'unconfirmed'):
            return True
    return False


def set_input_queue_paused(
    uow: SqliteUnitOfWork,
    *,
    scope: InputScope,
    paused: bool,
    expected_queue_revision: int,
    capability_revision: str,
    verify_authority: Callable[[], str],
) -> QueuePauseReceipt:
    """Apply an explicit pause or resume without mutating any accepted work.

    The verifier must prove current authority for the exact action and return
    its capability revision. The caller acquires the authority fence before
    opening the writer and publishes the receipt after commit. A pause can
    fence a ready session even without productive authority. A resume also
    requires its current generation and an active lease.
    """
    from .session_interaction import _conflict, _current_session, _scope_params

    uow.require_active_writer()
    if type(paused) is not bool:
        raise ValueError("A pause or resume must be explicit.")
    if verify_authority() != capability_revision or not capability_revision:
        raise _conflict("INPUT_CAPABILITY_CHANGED", "The queue control capability changed.")
    conn = uow.connection
    params = {**_scope_params(scope), "queue_revision": expected_queue_revision}
    if not _current_session(conn, params, require_active_lease=not paused):
        raise _conflict("INPUT_SESSION_CHANGED", "The exact session is unavailable for this queue control.")
    row = conn.execute("""
        SELECT revision, paused_owner_generation FROM session_interaction_queues
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
    """, params).fetchone()
    current = QueuePauseReceipt(*row) if row is not None else QueuePauseReceipt(0, None)
    if current.queue_revision != expected_queue_revision:
        raise _conflict("INPUT_REVISION_CHANGED", "The queue changed. Review it before changing its pause state.")
    if current.paused == paused:
        return current
    if not paused and has_unresolved_interrupt(conn, scope.session):
        raise _conflict("INPUT_INTERRUPT_UNRESOLVED", "Wait for the interrupt outcome before resuming the queue.")
    if current.queue_revision == MAX_SQLITE_INTEGER:
        raise _conflict("INPUT_REVISION_LIMIT", "The queue revision limit was reached.")

    generation = scope.generation.value if paused else None
    conn.execute("""
        INSERT INTO session_interaction_queues
            (server_id, executor_id, session_id, next_sequence, revision, paused_owner_generation)
        VALUES (:server_id, :executor_id, :session_id, 1, 1, :paused_owner_generation)
        ON CONFLICT (server_id, executor_id, session_id) DO UPDATE
        SET revision=revision+1, paused_owner_generation=excluded.paused_owner_generation
        WHERE revision=:queue_revision
    """, {**params, "paused_owner_generation": generation})
    return QueuePauseReceipt(current.queue_revision + 1, generation)
