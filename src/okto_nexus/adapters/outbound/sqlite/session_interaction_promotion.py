"""Bind an existing input to its explicit control in the admission writer."""

from ....domain.session_interaction import (
    MAX_SQLITE_INTEGER,
    InputDeliveryState,
    QueuedReceipt,
    may_promote,
)
from .session_interaction import _conflict, _current_session, _scope_params
from .session_interaction_capacity_attempts import read_capacity_attempt


def read_promotion_candidate(uow, *, scope, author, input_id):
    uow.require_active_writer()
    params = {**_scope_params(scope), 'input_id': input_id,
              'authority_ref': author.authority_ref, 'surface': author.surface}
    if not _current_session(uow.connection, params, require_active_lease=True):
        raise _conflict('INPUT_SESSION_CHANGED', 'The exact session is unavailable for reorientation.')
    row = uow.connection.execute("""
        SELECT i.*,q.revision AS queue_revision,q.paused_owner_generation,c.native_turn_id,c.confirmed_effect_revision,
               c.capability_revision AS steer_capability_revision
        FROM session_interaction_inputs i
        JOIN session_interaction_queues q USING(server_id,executor_id,session_id)
        LEFT JOIN session_interaction_controls c USING(server_id,executor_id,session_id,operation_id)
        WHERE i.server_id=:server_id AND i.executor_id=:executor_id AND i.session_id=:session_id
          AND i.owner_generation=:owner_generation AND i.binding_id=:binding_id
          AND i.workspace_id=:workspace_id AND i.workspace_binding_id=:workspace_binding_id
          AND i.agent_id=:agent_id AND i.authority_ref=:authority_ref AND i.surface=:surface
          AND i.input_id=:input_id
    """, params).fetchone()
    if row is None:
        raise _conflict('INPUT_NOT_OWNED', 'There is no matching input for reorientation.')
    return row


def require_promotable_input(uow, *, scope, row, now, expected_queue_revision, expected_input_revision):
    if (row['queue_revision'] != expected_queue_revision or row['input_revision'] != expected_input_revision
            or MAX_SQLITE_INTEGER in (row['queue_revision'], row['input_revision'])):
        raise _conflict('INPUT_REVISION_CHANGED', 'The input or queue changed. Review it before reorientation.')
    if (not may_promote(InputDeliveryState(row['status'])) or row['operation_id'] is not None
            or row['possible_effect'] or row['paused_owner_generation'] is not None
            or row['expires_at'] <= now.isoformat()):
        raise _conflict('INPUT_NOT_PROMOTABLE', 'The input is no longer available for reorientation.')
    attempt = read_capacity_attempt(uow, session=scope.session)
    if attempt is not None and attempt.input_id == row['input_id']:
        raise _conflict('INPUT_CAPACITY_PENDING', 'The pending delivery must be resolved before reorientation.')


def link_promoted_input(uow, *, scope, row, operation_id):
    """Link the already admitted R4 steer operation and retire next-turn eligibility."""
    uow.require_active_writer()
    params = {**_scope_params(scope), 'input_id': row['input_id'], 'input_revision': row['input_revision'],
              'queue_revision': row['queue_revision'], 'operation_id': operation_id}
    linked = uow.connection.execute("""
        UPDATE session_interaction_inputs
        SET operation_id=:operation_id,status='DISPATCHING',input_revision=input_revision+1
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND input_id=:input_id AND owner_generation=:owner_generation AND input_revision=:input_revision
          AND status='QUEUED' AND operation_id IS NULL AND possible_effect=0
    """, params).rowcount
    bumped = uow.connection.execute("""
        UPDATE session_interaction_queues SET revision=revision+1
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND revision=:queue_revision
    """, params).rowcount
    if linked != 1 or bumped != 1:
        raise _conflict('INPUT_REVISION_CHANGED', 'The input or queue changed during reorientation.')
    return QueuedReceipt(row['input_id'], row['enqueue_sequence'], row['input_revision'] + 1,
                         row['queue_revision'] + 1, InputDeliveryState.DISPATCHING, operation_id, False)
