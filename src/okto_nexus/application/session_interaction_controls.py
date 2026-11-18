"""Admit an exact control and its durable queue barrier in one writer."""

from dataclasses import asdict

from ..adapters.outbound.sqlite.session_interaction_queue_controls import (
    is_input_queue_paused,
    set_input_queue_paused,
)
from ..domain.attention import digest
from ..domain.execution.keys import SessionKey, SessionOwnerGeneration
from ..domain.session_interaction import InputAuthor, InputScope
from ..errors import ErrorCode, OktoNexusError
from .execution_admission import submit_execution_operation
from .execution_domain_delivery import DeliveryTransactionFactory
from .execution_intents import resolve_execution_intent
from .session_interaction_authority import require_human_queue_control


def request_exact_human_interrupt(*, factory, access, authority_fence, current_interrupt_revision,
                                  scope, author, client_intent_id, native_turn_id, capability_revision,
                                  expected_queue_revision, fresh_publications, remote_ready):
    """Route an exact native target through the existing R4 interrupt path."""
    if type(native_turn_id) is not str or not 1 <= len(native_turn_id) <= 160 or not native_turn_id.isprintable():
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'An exact native turn ID is required.', {})
    if type(client_intent_id) is not str or not 1 <= len(client_intent_id) <= 160 or not client_intent_id.isprintable():
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'An interrupt client intent ID is required.', {})
    with authority_fence() as resolve_human, factory.unit_of_work() as uow:
        context = require_human_queue_control(uow, access=access, author=author, resolve_human=resolve_human)
        borrowed = DeliveryTransactionFactory(uow)
        intent_key = 'session-interrupt-' + digest({'author': asdict(author), 'intent': client_intent_id})
        common = {'actor_agent_id': 'operator', 'context': context, 'access': access,
                  'fresh_publications': fresh_publications, 'remote_ready': remote_ready}
        resolved = resolve_execution_intent(borrowed, request={
            'client_intent_id': intent_key, 'intent': 'turn.interrupt', 'agent_id': scope.agent_id,
            'binding_id': scope.binding_id, 'workspace_binding_id': scope.workspace_binding_id,
            'session_id': scope.session.session_id,
            'target': {'kind': 'native_turn_id', 'expected_turn_id': native_turn_id},
        }, **common)
        exact = {**asdict(scope.session), 'binding_id': scope.binding_id, 'workspace_id': scope.workspace_id,
                 'workspace_binding_id': scope.workspace_binding_id, 'agent_id': scope.agent_id,
                 'session_owner_generation': scope.generation.value}
        if any(resolved['scope'].get(key) != value for key, value in exact.items()):
            raise OktoNexusError(ErrorCode.CONFLICT, 'The interrupt belongs to a different session scope.', {})
        if not resolved['can_submit']:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The exact interrupt is unavailable.', {'blockers': resolved['blockers']})

        operation_id = resolved['operation_id']
        existing = uow.connection.execute("""
            SELECT 1 FROM execution_operations WHERE server_id=? AND executor_id=? AND operation_id=?
        """, (scope.session.server_id, scope.session.executor_id, operation_id)).fetchone()
        identity = (scope.session.server_id, scope.session.executor_id, operation_id)
        control = (scope.session.session_id, scope.generation.value, author.authority_ref, author.surface,
                   capability_revision, native_turn_id)
        if existing is None:
            set_input_queue_paused(uow, scope=scope, paused=True, expected_queue_revision=expected_queue_revision,
                capability_revision=capability_revision,
                verify_authority=lambda: current_interrupt_revision(uow, scope, native_turn_id))
        else:
            prior = uow.connection.execute("""
                SELECT session_id,owner_generation,authority_ref,surface,capability_revision,native_turn_id
                FROM session_interaction_controls WHERE server_id=? AND executor_id=? AND operation_id=?
            """, identity).fetchone()
            if prior is None or tuple(prior) != control:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The retained interrupt has different authority or target.', {})

        operation = submit_execution_operation(borrowed, request={key: resolved[key] for key in (
            'client_intent_id', 'operation_id', 'intent_hash', 'resolution_revision')}, **common)
        if existing is None:
            uow.connection.execute("""
                INSERT INTO session_interaction_controls(server_id,executor_id,operation_id,session_id,owner_generation,
                    authority_ref,surface,capability_revision,native_turn_id) VALUES (?,?,?,?,?,?,?,?,?)
            """, (*identity, *control))
        return operation


def require_interrupt_send_authority(uow, *, access, control, scope, semantic, resolve_human,
                                     current_interrupt_revision):
    if resolve_human is None or current_interrupt_revision is None:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The interrupt author cannot be verified for this send.', {})
    session = SessionKey(scope['server_id'], scope['executor_id'], scope['session_id'])
    target = {'kind': 'native_turn_id', 'expected_turn_id': control['native_turn_id']}
    if (control['session_id'] != session.session_id or control['owner_generation'] != scope['session_owner_generation']
            or semantic['action'] != 'turn.interrupt' or semantic['target'] != target
            or not is_input_queue_paused(uow.connection, session)):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The exact interrupt or its queue barrier changed before send.', {})
    require_human_queue_control(uow, access=access, author=InputAuthor(control['authority_ref'], control['surface']),
                                resolve_human=resolve_human)
    exact = InputScope(session, SessionOwnerGeneration(scope['session_owner_generation']), scope['binding_id'],
                       scope['workspace_id'], scope['workspace_binding_id'], scope['agent_id'])
    if current_interrupt_revision(uow, exact, control['native_turn_id']) != control['capability_revision']:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The exact interrupt capability changed before send.', {})
