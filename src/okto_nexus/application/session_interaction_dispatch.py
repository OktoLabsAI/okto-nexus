"""Prepare the next input through the existing R4 admission transaction."""

import json

from nexus_connector_core import CapacityConsumption, CapacityReservation

from ..adapters.outbound.sqlite.session_interaction import (
    prepare_dispatch_head,
    stage_dispatch,
)
from ..domain.execution.keys import SessionKey, SessionOwnerGeneration
from ..domain.runtime_context import RuntimeRequestContext
from ..domain.session_interaction import InputAuthor, InputScope
from ..errors import ErrorCode, OktoNexusError
from .execution_admission import submit_execution_operation
from .execution_domain_delivery import DeliveryTransactionFactory
from .execution_intents import resolve_execution_intent
from .execution_native_facts import stamp
from .session_interaction_authority import require_session_input_authority


def admit_held_input(uow, *, factory, access, resolve_human, current_capability_revision,
                     scope, reservation, fresh_publications, remote_ready) -> CapacityConsumption:
    """Admit exactly the FIFO head without performing a native write.

    The caller holds the human authority fence and one execution writer and
    rolls the transaction back on any refusal. The reservation comes from
    the authenticated host, outside the writer. The shared pump waits for
    confirmed host consumption of the returned canonical identity.
    """
    head = prepare_dispatch_head(uow, scope=scope, now=stamp(access.clock.now_iso()))
    if (head is None or head.source_grant is None or type(reservation) is not CapacityReservation
            or reservation.state != 'HELD' or reservation.remaining_ms <= 0
            or reservation.request.unit != 'next_turn'
            or reservation.request.attempt_id != f'{head.input_id}:{head.input_revision}'):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The input or its capacity reservation changed.', {})
    grant = require_session_input_authority(uow, factory=factory, access=access, scope=scope,
                                           author=head.author, resolve_human=resolve_human)
    if grant != head.source_grant or current_capability_revision(uow, scope) != head.capability_revision:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The input authority or capability changed.', {})

    borrowed = DeliveryTransactionFactory(uow)
    context = RuntimeRequestContext('operator', 'operator_session', trusted_local_operator=True)
    common = {'actor_agent_id': 'operator', 'context': context, 'access': access,
              'fresh_publications': fresh_publications, 'remote_ready': remote_ready}
    resolved = resolve_execution_intent(borrowed, request={
        'client_intent_id': 'session-input-' + head.input_id, 'intent': 'turn.submit',
        'agent_id': scope.agent_id, 'binding_id': scope.binding_id, 'workspace_binding_id': scope.workspace_binding_id,
        'session_id': scope.session.session_id, 'text': head.text,
    }, **common)
    if not resolved['can_submit']:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The session input cannot be admitted.', {'blockers': resolved['blockers']})
    _, reused = submit_execution_operation(borrowed, request={key: resolved[key] for key in (
        'client_intent_id', 'operation_id', 'intent_hash', 'resolution_revision')}, **common)
    if reused:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The session input already has a canonical operation.', {})
    return stage_dispatch(uow, scope=scope, head=head, operation_id=resolved['operation_id'], reservation=reservation,
                          now=stamp(access.clock.now_iso()))


def require_input_send_authority(uow, *, factory, access, linked, scope, lease, intent_hash,
                                 resolve_human, current_capability_revision):
    """Revalidate the original human authority at the existing R4 send cut."""
    if resolve_human is None or current_capability_revision is None:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The input author cannot be verified for this send.', {})
    if (linked['status'] != 'DISPATCHING' or linked['possible_effect'] or linked['source_grant_id'] is None
            or any(linked[field] != scope[field] for field in (
                'server_id', 'executor_id', 'session_id', 'agent_id', 'binding_id', 'workspace_id', 'workspace_binding_id'))
            or linked['owner_generation'] != scope['session_owner_generation']):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The staged input or its scope changed.', {})
    reservation = CapacityReservation.from_dict(json.loads(linked['capacity_reservation_json']))
    reserved_scope = reservation.request.scope.to_dict()
    if (lease is None or reservation.state != 'CONSUMED' or reservation.consumption is None
            or reservation.consumption.turn_operation_id != linked['operation_id']
            or reservation.consumption.turn_intent_hash != intent_hash
            or reservation.request.scope.connection_generation != lease['connection_generation']
            or any(reserved_scope.get(key) != value for key, value in scope.items())):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The staged input capacity belongs to a different send.', {})
    exact = InputScope(SessionKey(scope['server_id'], scope['executor_id'], scope['session_id']),
        SessionOwnerGeneration(scope['session_owner_generation']), scope['binding_id'], scope['workspace_id'],
        scope['workspace_binding_id'], scope['agent_id'])
    grant = require_session_input_authority(uow, factory=factory, access=access, scope=exact,
        author=InputAuthor(linked['authority_ref'], linked['surface']), resolve_human=resolve_human)
    if (grant != (linked['source_grant_id'], linked['source_grant_revision'])
            or current_capability_revision(uow, exact) != linked['capability_revision']):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The input authority or capability changed before send.', {})
