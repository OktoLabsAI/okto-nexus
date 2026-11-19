"""Admit an exact control and its durable queue barrier in one writer."""

from dataclasses import asdict

from ..adapters.outbound.sqlite.execution_receipts import (
    read_execution_operation_history,
)
from ..adapters.outbound.sqlite.session_interaction_interrupt_targets import (
    interrupt_target_status,
)
from ..adapters.outbound.sqlite.session_interaction_queue_controls import (
    has_unresolved_interrupt,
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
from .execution_session_views import read_execution_session
from .session_interaction_authority import require_human_queue_control


def _intent_key(author, client_intent_id):
    return 'session-interrupt-' + digest({'author': asdict(author), 'intent': client_intent_id})


def _exact_scope(scope):
    return {**asdict(scope.session), 'binding_id': scope.binding_id, 'workspace_id': scope.workspace_id,
            'workspace_binding_id': scope.workspace_binding_id, 'agent_id': scope.agent_id,
            'session_owner_generation': scope.generation.value}


def request_exact_human_interrupt(*, factory, access, authority_fence, current_interrupt_target,
                                  scope, author, client_intent_id, native_turn_id, capability_revision,
                                  expected_queue_revision, fresh_publications, remote_ready, verify_command=None,
                                  verify_presenter=None):
    """Route an exact native target through the existing R4 interrupt path."""
    if type(native_turn_id) is not str or not 1 <= len(native_turn_id) <= 160 or not native_turn_id.isprintable():
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'An exact native turn ID is required.', {})
    if type(client_intent_id) is not str or not 1 <= len(client_intent_id) <= 160 or not client_intent_id.isprintable():
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'An interrupt client intent ID is required.', {})
    with authority_fence() as resolve_human, factory.unit_of_work() as uow:
        context = require_human_queue_control(uow, access=access, author=author, resolve_human=resolve_human)
        if verify_presenter is not None:
            verify_presenter(uow, resolve_human)
        borrowed = DeliveryTransactionFactory(uow)
        common = {'actor_agent_id': 'operator', 'context': context, 'access': access,
                  'fresh_publications': fresh_publications, 'remote_ready': remote_ready}
        resolved = resolve_execution_intent(borrowed, request={
            'client_intent_id': _intent_key(author, client_intent_id), 'intent': 'turn.interrupt', 'agent_id': scope.agent_id,
            'binding_id': scope.binding_id, 'workspace_binding_id': scope.workspace_binding_id,
            'session_id': scope.session.session_id,
            'target': {'kind': 'native_turn_id', 'expected_turn_id': native_turn_id},
        }, **common)
        if any(resolved['scope'].get(key) != value for key, value in _exact_scope(scope).items()):
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
            if verify_command is not None:
                verify_command(uow)
            if has_unresolved_interrupt(uow.connection, scope.session):
                raise OktoNexusError(ErrorCode.CONFLICT, 'An interrupt is already pending in this session.', {})
            target = current_interrupt_target(uow, scope)
            if target is None or target.native_id != native_turn_id or target.revision != capability_revision:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The exact interrupt target changed.', {})
            set_input_queue_paused(uow, scope=scope, paused=True, expected_queue_revision=expected_queue_revision,
                capability_revision=capability_revision, verify_authority=lambda: target.revision)
        else:
            prior = uow.connection.execute("""
                SELECT session_id,owner_generation,authority_ref,surface,capability_revision,target_ref
                FROM session_interaction_controls WHERE server_id=? AND executor_id=? AND operation_id=?
            """, identity).fetchone()
            if prior is None or tuple(prior) != control:
                raise OktoNexusError(ErrorCode.CONFLICT, 'The retained interrupt has different authority or target.', {})

        operation = submit_execution_operation(borrowed, request={key: resolved[key] for key in (
            'client_intent_id', 'operation_id', 'intent_hash', 'resolution_revision')}, **common)
        if existing is None:
            uow.connection.execute("""
                INSERT INTO session_interaction_controls(server_id,executor_id,operation_id,session_id,owner_generation,
                    authority_ref,surface,capability_revision,target_ref) VALUES (?,?,?,?,?,?,?,?,?)
            """, (*identity, *control))
            uow.connection.execute("""
                INSERT INTO session_interaction_interrupt_targets
                    (server_id,executor_id,operation_id,target_operation_id,target_stream_epoch) VALUES (?,?,?,?,?)
            """, (*identity, target.operation_id, target.stream_epoch))
        return operation


def read_human_interrupt_receipt(factory, *, access, resolve_human, scope, author, client_intent_id,
                                 current_interrupt_target=None):
    """Recover the original interrupt for this login and scope without admitting work."""
    with factory.unit_of_work(write=False) as uow:
        context = require_human_queue_control(uow, access=access, author=author, resolve_human=resolve_human)
        view = read_execution_session(factory, server_id=scope.session.server_id,
            executor_id=scope.session.executor_id, session_id=scope.session.session_id, context=context, access=access, _uow=uow)
        exact = _exact_scope(scope)
        if (view['scope']['session_owner_generation'] < scope.generation.value
                or any(view['scope'][key] != value for key, value in exact.items() if key != 'session_owner_generation')):
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'The interrupt receipt was not found in this scope.', {})
        row = uow.connection.execute("""
            SELECT o.operation_id, c.target_ref AS native_turn_id, t.target_operation_id, t.target_stream_epoch
            FROM execution_client_intents i
            JOIN execution_operations o ON o.server_id=i.server_id AND o.operation_id=i.operation_id
              AND o.actor_agent_id=i.actor_agent_id
            JOIN session_interaction_controls c ON c.server_id=o.server_id AND c.executor_id=o.executor_id
              AND c.operation_id=o.operation_id
            LEFT JOIN session_interaction_interrupt_targets t ON t.server_id=c.server_id
              AND t.executor_id=c.executor_id AND t.operation_id=c.operation_id
            WHERE i.server_id=:server_id AND i.actor_agent_id='operator' AND i.client_intent_id=:intent
              AND o.executor_id=:executor_id AND o.session_id=:session_id AND o.action='turn.interrupt'
              AND o.binding_id=:binding_id AND o.workspace_id=:workspace_id
              AND o.workspace_binding_id=:workspace_binding_id AND o.subject_agent_id=:agent_id
              AND c.session_id=:session_id AND c.owner_generation=:session_owner_generation
              AND c.authority_ref=:authority_ref AND c.surface=:surface
        """, {**exact, 'intent': _intent_key(author, client_intent_id), **asdict(author)}).fetchone()
        if row is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'The interrupt receipt was not found in this scope.', {})
        operation = read_execution_operation_history(DeliveryTransactionFactory(uow), server_id=scope.session.server_id,
            executor_id=scope.session.executor_id, operation_id=row['operation_id'],
            subject_agent_id=scope.agent_id).public_view()
        target_status = interrupt_target_status(uow.connection, exact, row)
        if (target_status == 'unconfirmed' and current_interrupt_target is not None
                and operation['error'] and not operation['possible_effect'] and row['target_operation_id'] is not None):
            live = current_interrupt_target(uow, scope)
            if (live and (live.operation_id, live.stream_epoch, live.native_id)
                    == (row['target_operation_id'], row['target_stream_epoch'], row['native_turn_id'])):
                target_status = 'running'
        pending = uow.connection.execute("""
            SELECT COUNT(*) FROM session_interaction_pending_inputs
            WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
              AND owner_generation=:session_owner_generation AND binding_id=:binding_id AND workspace_id=:workspace_id
              AND workspace_binding_id=:workspace_binding_id AND agent_id=:agent_id
              AND status NOT IN ('ACCEPTED_NATIVE','EXPIRED','CANCELLED')
        """, exact).fetchone()[0]
        operation['interrupt'] = {'target_status': target_status,
            'queue_paused': is_input_queue_paused(uow.connection, scope.session), 'pending_count': pending}
        return operation


def require_interrupt_send_authority(uow, *, access, control, scope, semantic, resolve_human,
                                     current_interrupt_revision):
    if resolve_human is None or current_interrupt_revision is None:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The interrupt author cannot be verified for this send.', {})
    session = SessionKey(scope['server_id'], scope['executor_id'], scope['session_id'])
    target = {'kind': 'native_turn_id', 'expected_turn_id': control['target_ref']}
    if (control['session_id'] != session.session_id or control['owner_generation'] != scope['session_owner_generation']
            or semantic['action'] != 'turn.interrupt' or semantic['target'] != target
            or not is_input_queue_paused(uow.connection, session)):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The exact interrupt or its queue barrier changed before send.', {})
    require_human_queue_control(uow, access=access, author=InputAuthor(control['authority_ref'], control['surface']),
                                resolve_human=resolve_human)
    exact = InputScope(session, SessionOwnerGeneration(scope['session_owner_generation']), scope['binding_id'],
                       scope['workspace_id'], scope['workspace_binding_id'], scope['agent_id'])
    if current_interrupt_revision(uow, exact, control['target_ref']) != control['capability_revision']:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The exact interrupt capability changed before send.', {})
