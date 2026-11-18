"""Promote an owned queued input to one exact, explicitly confirmed steer."""

from dataclasses import asdict

from ..adapters.outbound.sqlite.session_interaction import accept_input
from ..adapters.outbound.sqlite.session_interaction_promotion import (
    link_promoted_input,
    read_promotion_candidate,
    require_promotable_input,
)
from ..adapters.outbound.sqlite.session_interaction_queue_controls import (
    has_unresolved_interrupt,
)
from ..domain.execution.keys import SessionKey, SessionOwnerGeneration
from ..domain.session_interaction import (
    InputAuthor,
    InputDeliveryState,
    InputScope,
    QueuedReceipt,
)
from ..errors import ErrorCode, OktoNexusError
from .execution_admission import submit_execution_operation
from .execution_domain_delivery import DeliveryTransactionFactory
from .execution_intents import resolve_execution_intent
from .execution_native_facts import stamp
from .session_interaction_authority import (
    require_human_queue_control,
    require_session_input_authority,
)


def promote_queued_human_input(*, factory, access, authority_fence, current_steer_revisions,
                               scope, author, input_id, native_turn_id, capability_revision,
                               confirmed_effect_revision, expected_queue_revision, expected_input_revision,
                               fresh_publications, remote_ready):
    _validate_ids(input_id, native_turn_id, capability_revision, confirmed_effect_revision)
    with authority_fence() as resolve_human, factory.unit_of_work() as uow:
        context = require_human_queue_control(uow, access=access, author=author, resolve_human=resolve_human)
        return _promote(uow, factory=factory, access=access, scope=scope, author=author, context=context,
            resolve_human=resolve_human, current_steer_revisions=current_steer_revisions,
            input_id=input_id, native_turn_id=native_turn_id, revisions=(capability_revision, confirmed_effect_revision),
            expected_queue_revision=expected_queue_revision, expected_input_revision=expected_input_revision,
            fresh_publications=fresh_publications, remote_ready=remote_ready)


def steer_human_input(*, factory, access, authority_fence, current_steer_revisions,
                      scope, author, client_intent_id, text, native_turn_id, capability_revision,
                      confirmed_effect_revision, expected_queue_revision, fresh_publications, remote_ready,
                      verify_command=None):
    """Accept and link new text in one writer, with no observable FIFO intake on refusal."""
    _validate_ids(client_intent_id, native_turn_id, capability_revision, confirmed_effect_revision)
    _require_plain_text(text)
    revisions = (capability_revision, confirmed_effect_revision)
    with authority_fence() as resolve_human, factory.unit_of_work() as uow:
        context = require_human_queue_control(uow, access=access, author=author, resolve_human=resolve_human)

        def verify_intake():
            if verify_command is not None:
                verify_command(uow)
            row = uow.connection.execute("""
                SELECT revision FROM session_interaction_queues
                WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
            """, asdict(scope.session)).fetchone()
            if expected_queue_revision != (row['revision'] if row else 0):
                raise OktoNexusError(ErrorCode.CONFLICT, 'The session queue changed before reorientation.', {})
            return require_session_input_authority(uow, factory=factory, access=access, scope=scope,
                                                    author=author, resolve_human=resolve_human)

        admitted = accept_input(uow, scope=scope, author=author, client_intent_id=client_intent_id,
            capability_revision=capability_revision, text=text, now=stamp(access.clock.now_iso()),
            verify_new_authority=verify_intake, steer=(native_turn_id, *revisions))
        return _promote(uow, factory=factory, access=access, scope=scope, author=author, context=context,
            resolve_human=resolve_human, current_steer_revisions=current_steer_revisions,
            input_id=admitted.input_id, native_turn_id=native_turn_id, revisions=revisions,
            expected_queue_revision=admitted.queue_revision, expected_input_revision=admitted.input_revision,
            fresh_publications=fresh_publications, remote_ready=remote_ready)


def _validate_ids(*values):
    if any(type(value) is not str or not 1 <= len(value) <= 160 or not value.isprintable() for value in values):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'An exact turn and confirmed effect are required.', {})


def _require_plain_text(text):
    if isinstance(text, str) and text.lstrip().startswith(('/', '!')):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Commands are unavailable in this message input.', {})


def _promote(uow, *, factory, access, scope, author, context, resolve_human, current_steer_revisions,
             input_id, native_turn_id, revisions, expected_queue_revision, expected_input_revision,
             fresh_publications, remote_ready):
    row = read_promotion_candidate(uow, scope=scope, author=author, input_id=input_id)
    if row['confirmed_effect_revision'] is not None:
        retained = (row['steer_capability_revision'], row['confirmed_effect_revision'])
        if retained != revisions or row['native_turn_id'] != native_turn_id:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The retained reorientation targets a different effect.', {})
        return QueuedReceipt(input_id, row['enqueue_sequence'], row['input_revision'], row['queue_revision'],
                             InputDeliveryState(row['status']), row['operation_id'], bool(row['possible_effect']),
                             steer_submitted=bool(row['steer_submitted']), reorientation=True)
    require_promotable_input(uow, scope=scope, row=row, now=stamp(access.clock.now_iso()),
        expected_queue_revision=expected_queue_revision, expected_input_revision=expected_input_revision)
    _require_plain_text(row['content'])
    _require_authority(uow, factory=factory, access=access, linked=row, scope=scope, author=author,
        resolve_human=resolve_human, current_steer_revisions=current_steer_revisions,
        native_turn_id=native_turn_id, revisions=revisions)
    borrowed = DeliveryTransactionFactory(uow)
    options = {'actor_agent_id': 'operator', 'context': context, 'access': access,
               'fresh_publications': fresh_publications, 'remote_ready': remote_ready}
    resolved = resolve_execution_intent(borrowed, request={
        'client_intent_id': 'session-input-steer-' + input_id, 'intent': 'turn.steer',
        'agent_id': scope.agent_id, 'binding_id': scope.binding_id, 'workspace_binding_id': scope.workspace_binding_id,
        'session_id': scope.session.session_id, 'text': row['content'],
        'target': {'kind': 'native_turn_id', 'expected_turn_id': native_turn_id},
    }, **options)
    exact = {**asdict(scope.session), 'binding_id': scope.binding_id, 'workspace_id': scope.workspace_id,
             'workspace_binding_id': scope.workspace_binding_id, 'agent_id': scope.agent_id,
             'session_owner_generation': scope.generation.value}
    if any(resolved['scope'].get(key) != value for key, value in exact.items()) or not resolved['can_submit']:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The exact session cannot admit this reorientation.', {})
    _, reused = submit_execution_operation(borrowed, request={key: resolved[key] for key in (
        'client_intent_id', 'operation_id', 'intent_hash', 'resolution_revision')}, **options)
    if reused:
        raise OktoNexusError(ErrorCode.CONFLICT, 'A different operation already owns this input.', {})
    operation_id = resolved['operation_id']
    uow.connection.execute("""
        INSERT INTO session_interaction_controls (
            server_id,executor_id,operation_id,session_id,owner_generation,authority_ref,surface,
            capability_revision,native_turn_id,confirmed_effect_revision
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (scope.session.server_id, scope.session.executor_id, operation_id, scope.session.session_id,
          scope.generation.value, author.authority_ref, author.surface, revisions[0], native_turn_id, revisions[1]))
    return link_promoted_input(uow, scope=scope, row=row, operation_id=operation_id)


def _require_authority(uow, *, factory, access, linked, scope, author, resolve_human,
                       current_steer_revisions, native_turn_id, revisions):
    if has_unresolved_interrupt(uow.connection, scope.session):
        raise OktoNexusError(ErrorCode.CONFLICT, 'An interrupt is pending in this session.', {})
    if current_steer_revisions is None or current_steer_revisions(uow, scope, native_turn_id) != revisions:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The exact reorientation capability or effect changed.', {})
    grant = require_session_input_authority(uow, factory=factory, access=access, scope=scope,
                                            author=author, resolve_human=resolve_human)
    if grant != (linked['source_grant_id'], linked['source_grant_revision']):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The original input grant changed.', {})


def require_promoted_send_authority(uow, *, factory, access, linked, control, scope, semantic,
                                    resolve_human, current_steer_revisions):
    if resolve_human is None:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The reorientation author cannot be verified.', {})
    if (control is None or not control['confirmed_effect_revision'] or linked['status'] != 'DISPATCHING'
            or linked['possible_effect'] or linked['capacity_state'] is not None
            or control['authority_ref'] != linked['authority_ref'] or control['surface'] != linked['surface']
            or control['session_id'] != scope['session_id']
            or control['owner_generation'] != scope['session_owner_generation']
            or linked['owner_generation'] != scope['session_owner_generation']
            or any(linked[field] != scope[field] for field in (
                'server_id', 'executor_id', 'session_id', 'agent_id', 'binding_id', 'workspace_id', 'workspace_binding_id'
            ))
            or semantic['action'] != 'turn.steer' or semantic['payload'] != {'text': linked['content']}
            or semantic['target'] != {'kind': 'native_turn_id', 'expected_turn_id': control['native_turn_id']}):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The promoted input or exact turn changed before send.', {})
    exact = InputScope(SessionKey(scope['server_id'], scope['executor_id'], scope['session_id']),
        SessionOwnerGeneration(scope['session_owner_generation']), scope['binding_id'], scope['workspace_id'],
        scope['workspace_binding_id'], scope['agent_id'])
    _require_authority(uow, factory=factory, access=access, linked=linked, scope=exact,
        author=InputAuthor(linked['authority_ref'], linked['surface']), resolve_human=resolve_human,
        current_steer_revisions=current_steer_revisions, native_turn_id=control['native_turn_id'],
        revisions=(control['capability_revision'], control['confirmed_effect_revision']))
