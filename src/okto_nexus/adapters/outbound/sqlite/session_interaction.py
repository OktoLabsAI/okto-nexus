"""Durable acceptance of input before it becomes a canonical R4 operation.

Callers must hold a write unit of work and independently prove interactive
authority. This storage layer never wakes a worker or writes to a harness.
"""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ....domain.attention import digest
from ....domain.session_interaction import (
    InputAuthor,
    InputDeliveryState,
    InputScope,
    QueuedReceipt,
    validate_input_text,
)
from ....errors import ErrorCode, OktoNexusError
from .connection import SqliteUnitOfWork

MAX_PENDING = 50
PENDING_LIFETIME = timedelta(hours=24)


def _conflict(reason: str, message: str) -> OktoNexusError:
    return OktoNexusError(ErrorCode.CONFLICT, message, {"reason": reason})


def accept_input(
    uow: SqliteUnitOfWork,
    *,
    scope: InputScope,
    author: InputAuthor,
    client_intent_id: str,
    capability_revision: str,
    text: str,
    now: datetime,
) -> QueuedReceipt:
    """Allocate a FIFO sequence and persist one input in the caller's transaction.

    Publish the returned receipt only after the write unit of work commits.
    Exact-scope validation here is additional to the caller's authorization.
    """
    validate_input_text(text)
    if now.utcoffset() is None:
        raise ValueError("Server time must be timezone-aware.")
    now = now.astimezone(UTC)
    key = asdict(scope.session)
    fingerprint = digest({"scope": asdict(scope), "mode": "next_turn", "text": text})
    params = {
        **key, "authority_ref": author.authority_ref, "client_intent_id": client_intent_id,
        "owner_generation": scope.generation.value, "binding_id": scope.binding_id,
        "workspace_id": scope.workspace_id, "workspace_binding_id": scope.workspace_binding_id,
        "agent_id": scope.agent_id,
    }
    uow.require_active_writer()
    connection = uow.connection
    retained = connection.execute("""
        SELECT i.input_id, i.fingerprint, i.enqueue_sequence, i.input_revision, q.revision,
               i.status, i.operation_id, i.possible_effect
        FROM session_interaction_inputs i
        JOIN session_interaction_queues q USING (server_id, executor_id, session_id)
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND authority_ref=:authority_ref AND client_intent_id=:client_intent_id
    """, params).fetchone()
    if retained is not None:
        if retained["fingerprint"] != fingerprint:
            raise _conflict("INPUT_INTENT_CHANGED", "This input ID already identifies a different intent.")
        return QueuedReceipt(
            retained["input_id"], retained["enqueue_sequence"], retained["input_revision"],
            retained["revision"], InputDeliveryState(retained["status"]), retained["operation_id"],
            bool(retained["possible_effect"]),
        )

    valid = connection.execute("""
        SELECT 1 FROM execution_sessions s
        JOIN execution_bindings b
          ON b.server_id=s.server_id AND b.executor_id=s.executor_id AND b.binding_id=s.binding_id
        JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id
        JOIN execution_workspace_bindings w
          ON w.server_id=s.server_id AND w.executor_id=s.executor_id
          AND w.workspace_binding_id=s.workspace_binding_id AND w.workspace_id=s.workspace_id
        WHERE s.server_id=:server_id AND s.executor_id=:executor_id AND s.session_id=:session_id
          AND s.binding_id=:binding_id AND s.workspace_id=:workspace_id
          AND s.workspace_binding_id=:workspace_binding_id AND s.owner_generation=:owner_generation
          AND b.workspace_binding_id=:workspace_binding_id AND e.agent_id=:agent_id
          AND s.lifecycle_state IN ('READY', 'ACTIVE')
    """, params).fetchone()
    if valid is None:
        raise _conflict("INPUT_SESSION_CHANGED", "This exact session is unavailable. Reopen it to inspect its current scope.")
    pending = connection.execute("""
        SELECT count(*) FROM session_interaction_inputs
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND status IN ('QUEUED', 'DISPATCHING', 'REFUSED_BEFORE_SEND', 'DELIVERY_UNKNOWN',
                         'BLOCKED_AUTH', 'BLOCKED_SESSION', 'PAUSED')
    """, key).fetchone()[0]
    if pending >= MAX_PENDING:
        raise _conflict("INPUT_QUEUE_FULL", "This session has reached its pending input limit.")

    sequence, revision = connection.execute("""
        INSERT INTO session_interaction_queues
            (server_id, executor_id, session_id, next_sequence, revision)
        VALUES (:server_id, :executor_id, :session_id, 2, 1)
        ON CONFLICT (server_id, executor_id, session_id) DO UPDATE SET
            next_sequence=next_sequence+1, revision=revision+1
        RETURNING next_sequence-1, revision
    """, key).fetchone()
    input_id = "sin_" + uuid4().hex
    connection.execute("""
        INSERT INTO session_interaction_inputs (
            server_id, executor_id, session_id, owner_generation, binding_id, workspace_id, workspace_binding_id,
            agent_id, input_id, authority_ref, surface, client_intent_id, fingerprint, enqueue_sequence,
            capability_revision, content, status, created_at, expires_at
        ) VALUES (
            :server_id, :executor_id, :session_id, :owner_generation, :binding_id, :workspace_id, :workspace_binding_id,
            :agent_id, :input_id, :authority_ref, :surface, :client_intent_id, :fingerprint, :sequence,
            :capability_revision, :text, 'QUEUED', :created_at, :expires_at
        )
    """, {
        **params, "input_id": input_id, "surface": author.surface, "fingerprint": fingerprint,
        "sequence": sequence, "capability_revision": capability_revision, "text": text,
        "created_at": now.isoformat(), "expires_at": (now + PENDING_LIFETIME).isoformat(),
    })
    return QueuedReceipt(input_id, sequence, 0, revision, InputDeliveryState.QUEUED, None, False)
