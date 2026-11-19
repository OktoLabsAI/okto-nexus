"""Review and apply explicit reorientation against one proven native turn."""

from dataclasses import asdict

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ....adapters.outbound.execution.core_inventory import protocol_info
from ....adapters.outbound.sqlite.session_interaction_promotion import (
    read_promotion_candidate,
    require_promotable_input,
)
from ....adapters.outbound.sqlite.session_interaction_queue_controls import (
    has_unresolved_interrupt,
)
from ....application.execution_native_facts import stamp
from ....application.session_interaction_promotion import (
    promote_queued_human_input,
    steer_human_input,
)
from ....application.session_interaction_targets import (
    active_native_turn,
    active_pi_run,
    steer_effect_revisions,
)
from ....bootstrap.execution_authority import build_execution_access
from ....domain.session_interaction import InputAuthor
from ....errors import ErrorCode, OktoNexusError
from .dashboard_session_input import (
    _HEADERS,
    _error,
    _exact_view,
    _read_scope,
    _receipt_document,
    _runtime_error,
)
from .identity_ctx import runtime_request_context
from .operator_auth import COOKIE
from .session_interaction_contract import (
    NativeTurnTarget,
    ObservedRunTarget,
    PromoteInput,
    SteerAvailability,
    SteerInput,
    SteerInputPreview,
    SteerTargetView,
)


def review_exact_steer(uow, scope, revision_for):
    queue = uow.connection.execute("""
        SELECT revision,paused_owner_generation FROM session_interaction_queues
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
    """, asdict(scope.session)).fetchone()
    if (revision_for is None or (queue and queue['paused_owner_generation'] is not None)
            or has_unresolved_interrupt(uow.connection, scope.session)):
        return None
    turn = active_native_turn(uow, scope, current_next_turn_revision=revision_for)
    run = active_pi_run(uow, scope, current_next_turn_revision=revision_for) if turn is None else None
    proven = turn or run
    revisions = steer_effect_revisions(proven) if proven is not None else None
    if revisions is None:
        return None
    target = (NativeTurnTarget(kind='native_turn', turn_id=turn.native_id) if turn is not None
              else ObservedRunTarget(kind='observed_run', run_ref=run.run_ref))
    return SteerTargetView(target=target,
        capability_revision=revisions[0], effect_revision=revisions[1], queue_revision=queue['revision'] if queue else 0,
        effect='next_boundary' if run is not None else 'same_turn')


async def steer_response(session_id, body, request, operation, arguments, *, surface='web'):
    if not getattr(request.state, 'operator_session', False):
        return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to reorient a turn.')
    if body.scope.session_id != session_id or request.query_params:
        return _error(422, 'VALIDATION_ERROR', 'The reorientation must use the exact session scope.')
    observed = isinstance(body.target, ObservedRunTarget)
    target_ref = body.target.run_ref if observed else body.target.turn_id
    state = request.app.state
    options = getattr(state, 'session_input_dispatch_options', {})
    if not options:
        return _error(409, 'CONFLICT', 'Session interaction controls are disabled.')

    def admit():
        auth = state.operator_auth
        ref = auth.authority_reference(request.cookies.get(COOKIE), create=operation is steer_human_input)
        if ref is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'No input is available for this login and session.')
        receipt = operation(factory=state.deps.connection_factory, access=build_execution_access(state.deps),
            authority_fence=options['session_input_authority_fence'], current_steer_revisions=options['session_steer_revisions'],
            scope=body.input_scope(), author=InputAuthor(ref, surface), native_turn_id=target_ref, observed_run=observed,
            capability_revision=body.capability_revision, confirmed_effect_revision=body.confirmed_effect_revision,
            expected_queue_revision=body.expected_queue_revision, fresh_publications=state.inventory_fresh_publications,
            remote_ready=protocol_info()['remote_execution_ready'], **arguments)
        return _receipt_document(body.scope, body.expected_session_generation, receipt)

    try:
        return JSONResponse(await anyio.to_thread.run_sync(admit), status_code=202, headers=_HEADERS)
    except OktoNexusError as error:
        return _runtime_error(error)

def build_router():
    router = APIRouter(prefix='/runtime/sessions/{session_id}')

    @router.get('/steer')
    async def review(session_id: str, request: Request):
        if not getattr(request.state, 'operator_session', False):
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to review reorientation.')
        input_id = request.query_params.get('input_id')
        try:
            document, scope = _read_scope(request, session_id, extra=('input_id',) if input_id is not None else ())
            if input_id is not None and (not 1 <= len(input_id) <= 160 or not input_id.isprintable()):
                raise ValueError('Invalid input identifier.')
        except ValueError:
            return _error(422, 'VALIDATION_ERROR', 'An exact session scope is required.')
        state = request.app.state
        factory = state.deps.connection_factory
        access = build_execution_access(state.deps)
        context = runtime_request_context()
        options = getattr(state, 'session_input_dispatch_options', {})

        def read():
            with factory.unit_of_work(write=False) as uow:
                _exact_view(factory, uow, context=context, access=access, document=document, scope=scope)
                control = review_exact_steer(uow, scope, options.get('session_input_capability_revision'))
                queued_input = None
                if control is not None and input_id is not None:
                    auth = state.operator_auth
                    ref = auth.authority_reference(request.cookies.get(COOKIE), create=False)
                    if ref is None or not auth.resolve_authority(ref):
                        raise OktoNexusError(ErrorCode.NOT_FOUND, 'No input is available for this login and session.')
                    row = read_promotion_candidate(uow, scope=scope, author=InputAuthor(ref, 'web'), input_id=input_id)
                    require_promotable_input(uow, scope=scope, row=row, now=stamp(access.clock.now_iso()),
                        expected_queue_revision=control.queue_revision, expected_input_revision=row['input_revision'])
                    content = row['content']
                    queued_input = SteerInputPreview(input_id=input_id, input_revision=row['input_revision'],
                        text_preview=content[:200], truncated=len(content) > 200)
                return SteerAvailability(scope=document, session_owner_generation=scope.generation.value,
                                         control=control, queued_input=queued_input).model_dump(mode='json')

        try:
            return JSONResponse(await anyio.to_thread.run_sync(read), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.post('/steer', status_code=202)
    async def steer(session_id: str, body: SteerInput, request: Request):
        return await steer_response(session_id, body, request, steer_human_input,
                           {'client_intent_id': body.client_intent_id, 'text': body.content[0].text})

    @router.post('/inputs/{input_id}/promote', status_code=202)
    async def promote(session_id: str, input_id: str, body: PromoteInput, request: Request):
        return await steer_response(session_id, body, request, promote_queued_human_input,
                           {'input_id': input_id, 'expected_input_revision': body.expected_input_revision})

    return router
