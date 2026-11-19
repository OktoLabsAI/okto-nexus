"""Dashboard interaction with one exact session under a real human login."""

from dataclasses import asdict
from functools import partial

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from nexus_connector_core.targeted_control_link import CLAUDE_OPERATION_STEER_CODEC, PI_RUN_CONTROL_CODEC

from ....adapters.outbound.execution.core_inventory import protocol_info
from ....adapters.outbound.sqlite.session_interaction_queue_controls import (
    has_unresolved_interrupt,
)
from ....application.execution_native_session_mapping import (
    read_managed_native_session,
    reviewed_pi_context,
)
from ....application.execution_session_views import read_execution_session
from ....application.session_interaction_authority import (
    cancel_human_input,
    change_human_queue_pause,
    enqueue_human_input,
)
from ....application.session_interaction_capability import queue_pause_revision
from ....application.session_interaction_controls import (
    read_human_interrupt_receipt,
    request_exact_human_interrupt,
)
from ....application.session_interaction_queue_view import (
    InputQueueCursor,
    read_session_input_queue,
)
from ....application.session_interaction_receipts import read_session_input_receipt
from ....application.session_interaction_targets import (
    ExactClaudeOperation,
    ExactPiRun,
    active_interrupt_target,
    negotiated_control_channel,
)
from ....bootstrap.execution_authority import build_execution_access
from ....domain.attention import digest
from ....domain.session_interaction import InputAuthor
from ....errors import ErrorCode, OktoNexusError
from .identity_ctx import get_authenticated_agent, runtime_request_context
from .operator_auth import COOKIE
from .session_interaction_contract import (
    CancelInput,
    ClaudeOperationTarget,
    EnqueueInput,
    ExactSessionScope,
    InputQueueEntry,
    InputQueueSnapshot,
    InputQueueState,
    InputReceipt,
    InterruptAvailability,
    InterruptInput,
    InterruptTargetView,
    NativeTurnTarget,
    ObservedRunTarget,
    QueuePauseChange,
)

_HEADERS = {'Cache-Control': 'no-store'}


def _read_scope(request, session_id, *, extra=()):
    fields = set(ExactSessionScope.model_fields) - {'session_id'}
    query = request.query_params
    if set(query) != fields | {'expected_session_generation', *extra} or len(query.multi_items()) != len(query):
        raise ValueError('An exact session scope is required.')
    raw_generation = query['expected_session_generation']
    if len(raw_generation) > 19 or not raw_generation.isascii() or not raw_generation.isdecimal():
        raise ValueError('The session owner generation must be positive.')
    document = ExactSessionScope(session_id=session_id, **{field: query[field] for field in fields})
    return document, document.input_scope(int(raw_generation))


def _error(status, code, message):
    from .app import v1_err

    response = v1_err(status, code, message, stage='session.interaction')
    response.headers.update(_HEADERS)
    return response


def _receipt_document(document, generation, receipt):
    return InputReceipt(scope=document, session_owner_generation=generation,
        input_id=receipt.input_id, enqueue_sequence=receipt.sequence, input_revision=receipt.input_revision,
        queue_revision=receipt.queue_revision, status=receipt.status, operation_id=receipt.operation_id,
        possible_effect=receipt.possible_effect, steer_submitted=receipt.steer_submitted,
        reorientation=receipt.reorientation, steer_boundary=receipt.steer_boundary,
        steer_compound=receipt.steer_compound).model_dump(mode='json', exclude={
            name for name in ('steer_boundary', 'steer_compound') if getattr(receipt, name) is None})


def _cancel_revision(_uow, scope):
    # Removing unsent work needs no productive capability or native grant.
    return 'sha256:' + digest({'action': 'queue.cancel.v1', 'scope': asdict(scope)})


def _queue_cursor(scope_digest, token):
    namespace, _, sequence = token.partition('.')
    if namespace != scope_digest or len(sequence) > 19 or not sequence.isascii() or not sequence.isdecimal():
        raise ValueError('The queue cursor does not match this session.')
    return int(sequence)


def _exact_view(factory, uow, *, context, access, document, scope):
    view = read_execution_session(factory, server_id=scope.session.server_id,
        executor_id=scope.session.executor_id, session_id=scope.session.session_id, context=context, access=access, _uow=uow)
    exact = {**document.model_dump(), 'session_owner_generation': scope.generation.value}
    if any(view['scope'][key] != value for key, value in exact.items()):
        raise OktoNexusError(ErrorCode.NOT_FOUND, 'The session is outside this scope.')
    return exact


def _interrupt_target_for(state):
    next_turn = getattr(state, 'session_input_dispatch_options', {}).get('session_input_capability_revision')
    return partial(active_interrupt_target, current_next_turn_revision=next_turn,
        remote_control_host=state.deps.runtime_availability.current_host) if next_turn is not None else None


def review_exact_interrupt(uow, scope, target_for):
    if target_for is None or has_unresolved_interrupt(uow.connection, scope.session):
        return None
    target = target_for(uow, scope)
    if target is None:
        return None
    row = uow.connection.execute("""
        SELECT revision FROM session_interaction_queues
        WHERE server_id=? AND executor_id=? AND session_id=?
    """, (scope.session.server_id, scope.session.executor_id, scope.session.session_id)).fetchone()
    if isinstance(target, ExactClaudeOperation):
        document = ClaudeOperationTarget(kind='claude_operation', operation_id=target.operation_id)
    elif isinstance(target, ExactPiRun):
        document = ObservedRunTarget(kind='observed_run', run_ref=target.run_ref)
    else:
        document = NativeTurnTarget(kind='native_turn', turn_id=target.native_id)
    return InterruptTargetView(target=document,
                               capability_revision=target.revision, queue_revision=row[0] if row else 0)


async def enqueue_input_response(session_id: str, body: EnqueueInput, request: Request, *, verify_command=None,
                                 surface='web'):
    if not getattr(request.state, 'operator_session', False):
        return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to send a message.')
    if body.scope.session_id != session_id or request.query_params:
        return _error(422, 'VALIDATION_ERROR', 'The message must use the exact session scope.')
    state = request.app.state
    options = getattr(state, 'session_input_dispatch_options', {})
    if not options:
        return _error(409, 'CONFLICT', 'Sending messages through the session queue is disabled.')
    auth = state.operator_auth

    def submit():
        reference = auth.authority_reference(request.cookies.get(COOKIE))
        if reference is None:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The operator login has expired.')
        receipt = enqueue_human_input(factory=state.deps.connection_factory,
            access=build_execution_access(state.deps), authority_fence=options['session_input_authority_fence'],
            current_capability_revision=options['session_input_capability_revision'], scope=body.input_scope(),
            author=InputAuthor(reference, surface), client_intent_id=body.client_intent_id,
            capability_revision=body.capability_revision, text=body.content[0].text, verify_command=verify_command)
        return _receipt_document(body.scope, body.expected_session_generation, receipt)

    try:
        return JSONResponse(await anyio.to_thread.run_sync(submit), status_code=202, headers=_HEADERS)
    except OktoNexusError as error:
        return _runtime_error(error)

async def interrupt_response(session_id: str, body: InterruptInput, request: Request, *, verify_command=None,
                             surface='web'):
    if not getattr(request.state, 'operator_session', False):
        return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to interrupt a turn.')
    if body.scope.session_id != session_id or request.query_params:
        return _error(422, 'VALIDATION_ERROR', 'The interrupt must use the exact session scope.')
    observed_run = isinstance(body.target, ObservedRunTarget)
    claude_operation = isinstance(body.target, ClaudeOperationTarget)
    target_ref = body.target.operation_id if claude_operation else body.target.run_ref if observed_run else body.target.turn_id
    state = request.app.state
    options = getattr(state, 'session_input_dispatch_options', {})
    if not options:
        return _error(409, 'CONFLICT', 'Session interaction controls are disabled.')

    def admit():
        ref = state.operator_auth.authority_reference(request.cookies.get(COOKIE))
        if ref is None:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The operator login has expired.')
        return request_exact_human_interrupt(factory=state.deps.connection_factory,
            access=build_execution_access(state.deps), authority_fence=options['session_input_authority_fence'],
            current_interrupt_target=_interrupt_target_for(state), scope=body.input_scope(),
            author=InputAuthor(ref, surface), client_intent_id=body.client_intent_id, native_turn_id=target_ref,
            observed_run=observed_run, claude_operation=claude_operation,
            capability_revision=body.capability_revision, expected_queue_revision=body.expected_queue_revision,
            fresh_publications=state.inventory_fresh_publications, remote_ready=protocol_info()['remote_execution_ready'],
            verify_command=verify_command)

    try:
        operation, reused = await anyio.to_thread.run_sync(admit)
        return JSONResponse(operation, status_code=200 if reused else 202, headers=_HEADERS)
    except OktoNexusError as error:
        return _runtime_error(error)

def build_router():
    router = APIRouter(prefix='/runtime/sessions/{session_id}')

    @router.get('/interaction')
    async def interaction(session_id: str, request: Request):
        if get_authenticated_agent() is None:
            return _error(401, 'AUTH_FAILED', 'Authentication is required.')
        try:
            document, scope = _read_scope(request, session_id)
        except ValueError:
            return _error(422, 'VALIDATION_ERROR', 'An exact session scope is required.')

        state = request.app.state
        revision_for = getattr(state, 'session_input_dispatch_options', {}).get('session_input_capability_revision')
        context = runtime_request_context()
        factory = state.deps.connection_factory
        access = build_execution_access(state.deps)
        signed_in = getattr(request.state, 'operator_session', False)

        def read():
            with factory.unit_of_work(write=False) as uow:
                exact = _exact_view(factory, uow, context=context, access=access, document=document, scope=scope)
                session = uow.connection.execute("""
                    SELECT s.stream_epoch,e.adapter_id,x.kind,x.owner_instance_id,x.generation FROM execution_sessions s
                    JOIN execution_executors x USING(server_id,executor_id)
                    LEFT JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id
                      AND b.binding_id=s.binding_id
                    LEFT JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id
                    WHERE s.server_id=? AND s.executor_id=? AND s.session_id=?
                    """,
                    (scope.session.server_id, scope.session.executor_id, session_id),
                ).fetchone()
                revision = revision_for(uow, scope) if revision_for is not None else None
                adapter = session['adapter_id']
                codec = {'pi_rpc': PI_RUN_CONTROL_CODEC, 'claude_stream': CLAUDE_OPERATION_STEER_CODEC}.get(adapter)
                supported_owner = session['kind'] == 'embedded'
                if revision is not None and codec is not None and session['kind'] == 'remote':
                    channel = negotiated_control_channel(scope, state.deps.runtime_availability.current_host, codec.revision)
                    supported_owner = channel is not None and (channel.connection_id, channel.connection_generation) == (
                        session['owner_instance_id'], session['generation'])
                pi = revision is not None and adapter == 'pi_rpc' and supported_owner
                mapping = read_managed_native_session(uow, scope) if pi else None
                exact_control = revision is not None and (adapter == 'codex_app_server'
                    or (mapping is not None and reviewed_pi_context(mapping)))
                claude_steer = (revision is not None and adapter == 'claude_stream' and supported_owner
                    and read_managed_native_session(uow, scope) is not None)
                claude_interrupt = (claude_steer and session['kind'] == 'embedded'
                    and isinstance(active_interrupt_target(uow, scope, current_next_turn_revision=revision_for),
                                   ExactClaudeOperation))
                return {'scope': exact, 'stream_epoch': session['stream_epoch'],
                        'interaction_enabled': revision_for is not None,
                        'interrupt_review_supported': exact_control or claude_interrupt,
                        'steer_review_supported': exact_control or claude_steer,
                        'next_turn': {'supported': revision is not None, 'capability_revision': revision,
                                      'human_login_required': not signed_in}}

        try:
            return JSONResponse(await anyio.to_thread.run_sync(read), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.post('/inputs', status_code=202)
    async def enqueue_input(session_id: str, body: EnqueueInput, request: Request):
        return await enqueue_input_response(session_id, body, request)

    async def input_receipt_for(session_id, request, surface):
        if not getattr(request.state, 'operator_session', False):
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to recover a receipt.')
        selector = 'input_id' if 'input_id' in request.query_params else 'client_intent_id'
        try:
            document, scope = _read_scope(request, session_id, extra=(selector,))
        except ValueError:
            return _error(422, 'VALIDATION_ERROR', 'An exact session scope and message intent are required.')
        intent = request.query_params[selector]
        if not 1 <= len(intent) <= 160 or not intent.isprintable():
            return _error(422, 'VALIDATION_ERROR', 'The message intent is invalid.')
        state = request.app.state
        auth = state.operator_auth

        def read():
            ref = auth.authority_reference(request.cookies.get(COOKIE), create=False)
            if ref is None:
                raise OktoNexusError(ErrorCode.NOT_FOUND, 'The input receipt was not found in this scope.')
            receipt = read_session_input_receipt(state.deps.connection_factory, access=build_execution_access(state.deps),
                resolve_human=auth.resolve_authority, scope=scope, author=InputAuthor(ref, surface),
                **{selector: intent})
            return _receipt_document(document, scope.generation.value, receipt)

        try:
            return JSONResponse(await anyio.to_thread.run_sync(read), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.get('/inputs/receipt')
    async def input_receipt(session_id: str, request: Request):
        return await input_receipt_for(session_id, request, 'web')

    @router.get('/terminal/inputs/receipt')
    async def terminal_input_receipt(session_id: str, request: Request):
        return await input_receipt_for(session_id, request, 'nexus_cli')

    @router.get('/presenter/inputs/receipt')
    async def presenter_input_receipt(session_id: str, request: Request):
        return await input_receipt_for(session_id, request, 'native_terminal')

    @router.get('/inputs')
    async def input_queue(session_id: str, request: Request):
        if not getattr(request.state, 'operator_session', False):
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to read the session queue.')
        options = set(request.query_params) & {'cursor', 'limit', 'pending_only'}
        try:
            document, scope = _read_scope(request, session_id, extra=options)
            pending = request.query_params.get('pending_only', 'false')
            if pending not in ('true', 'false'):
                raise ValueError('The pending input filter is invalid.')
            scope_digest = digest({'kind': 'session_input_queue.v1', 'scope': asdict(scope), 'pending_only': pending})
            raw_limit = request.query_params.get('limit', '25')
            if len(raw_limit) > 2 or not raw_limit.isascii() or not raw_limit.isdecimal():
                raise ValueError('The queue page limit is invalid.')
            limit = int(raw_limit)
            cursor = (InputQueueCursor(scope, _queue_cursor(scope_digest, request.query_params['cursor']))
                      if 'cursor' in options else None)
        except ValueError:
            return _error(422, 'VALIDATION_ERROR', 'An exact session scope and a valid queue cursor and limit are required.')
        state = request.app.state
        auth = state.operator_auth
        token = request.cookies.get(COOKIE)
        dispatch = getattr(state, 'session_input_dispatch_options', {})
        pause_revision_for = (partial(queue_pause_revision,
            current_next_turn_revision=dispatch['session_input_capability_revision']) if dispatch else None)

        def read():
            ref = auth.authority_reference(token, create=False)
            author = InputAuthor(ref, 'web') if ref else None

            def resolve(reference):
                return auth.resolve(token) if reference is None else auth.resolve_authority(reference)

            page = read_session_input_queue(state.deps.connection_factory, access=build_execution_access(state.deps),
                resolve_human=resolve, scope=scope, author=author, cursor=cursor, limit=limit,
                pending_only=pending == 'true', pause_revision_for=pause_revision_for)
            return InputQueueSnapshot(
                scope=document, session_owner_generation=scope.generation.value,
                queue_revision=page.queue_revision, paused=page.paused,
                cancel_capability_revision=_cancel_revision(None, scope) if dispatch else None,
                pause_capability_revision=page.pause_capability_revision,
                items=[InputQueueEntry(
                    scope=document, session_owner_generation=scope.generation.value,
                    input_id=item.input_id, enqueue_sequence=item.sequence, input_revision=item.input_revision,
                    queue_revision=page.queue_revision, status=item.status, operation_id=item.operation_id,
                    possible_effect=item.possible_effect, can_cancel=bool(dispatch) and item.can_cancel,
                    can_promote=bool(dispatch) and not page.paused and item.can_cancel and item.status == 'QUEUED',
                ) for item in page.items],
                next_cursor=f'{scope_digest}.{page.next_cursor.after_sequence}' if page.next_cursor else None,
            ).model_dump(mode='json')

        try:
            return JSONResponse(await anyio.to_thread.run_sync(read), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.post('/inputs/queue-state')
    async def set_queue_state(session_id: str, body: QueuePauseChange, request: Request):
        if not getattr(request.state, 'operator_session', False):
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to change the session queue.')
        if body.scope.session_id != session_id or request.query_params:
            return _error(422, 'VALIDATION_ERROR', 'The queue control must use the exact session scope.')
        state = request.app.state
        options = getattr(state, 'session_input_dispatch_options', {})
        if not options:
            return _error(409, 'CONFLICT', 'Session queue controls are disabled.')

        def change():
            ref = state.operator_auth.authority_reference(request.cookies.get(COOKIE))
            if ref is None:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The operator login has expired.')
            receipt = change_human_queue_pause(factory=state.deps.connection_factory,
                access=build_execution_access(state.deps), authority_fence=options['session_input_authority_fence'],
                current_pause_revision=partial(queue_pause_revision,
                    current_next_turn_revision=options['session_input_capability_revision']),
                scope=body.input_scope(), author=InputAuthor(ref, 'web'), paused=body.paused,
                capability_revision=body.capability_revision, expected_queue_revision=body.expected_queue_revision)
            return InputQueueState(scope=body.scope, session_owner_generation=body.expected_session_generation,
                                   queue_revision=receipt.queue_revision, paused=receipt.paused).model_dump(mode='json')

        try:
            return JSONResponse(await anyio.to_thread.run_sync(change), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.post('/inputs/{input_id}/cancel')
    async def cancel_input(session_id: str, input_id: str, body: CancelInput, request: Request):
        if not getattr(request.state, 'operator_session', False):
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to remove a queued message.')
        if body.scope.session_id != session_id or request.query_params or not 1 <= len(input_id) <= 160:
            return _error(422, 'VALIDATION_ERROR', 'The cancellation must use the exact input and session scope.')
        state = request.app.state
        options = getattr(state, 'session_input_dispatch_options', {})
        if not options:
            return _error(409, 'CONFLICT', 'Session queue controls are disabled.')

        def cancel():
            reference = state.operator_auth.authority_reference(request.cookies.get(COOKIE), create=False)
            if reference is None:
                raise OktoNexusError(ErrorCode.NOT_FOUND, 'The input is unavailable in this author and session scope.')
            receipt = cancel_human_input(factory=state.deps.connection_factory,
                access=build_execution_access(state.deps), authority_fence=options['session_input_authority_fence'],
                current_cancel_revision=_cancel_revision, scope=body.input_scope(), author=InputAuthor(reference, 'web'),
                input_id=input_id, capability_revision=body.capability_revision,
                expected_queue_revision=body.expected_queue_revision, expected_input_revision=body.expected_input_revision)
            return _receipt_document(body.scope, body.expected_session_generation, receipt)

        try:
            return JSONResponse(await anyio.to_thread.run_sync(cancel), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.get('/interrupt')
    async def interrupt_target(session_id: str, request: Request):
        if not getattr(request.state, 'operator_session', False):
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to inspect the current turn.')
        try:
            document, scope = _read_scope(request, session_id)
        except ValueError:
            return _error(422, 'VALIDATION_ERROR', 'An exact session scope is required.')
        state = request.app.state
        factory = state.deps.connection_factory
        context = runtime_request_context()
        access = build_execution_access(state.deps)
        target_for = _interrupt_target_for(state)

        def read():
            with factory.unit_of_work(write=False) as uow:
                _exact_view(factory, uow, context=context, access=access, document=document, scope=scope)
                control = review_exact_interrupt(uow, scope, target_for)
                return InterruptAvailability(scope=document, session_owner_generation=scope.generation.value,
                                             control=control).model_dump(mode='json')

        try:
            return JSONResponse(await anyio.to_thread.run_sync(read), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.post('/interrupt', status_code=202)
    async def interrupt(session_id: str, body: InterruptInput, request: Request):
        return await interrupt_response(session_id, body, request)

    async def interrupt_receipt_for(session_id, request, surface):
        if not getattr(request.state, 'operator_session', False):
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to recover an interrupt receipt.')
        try:
            _, scope = _read_scope(request, session_id, extra=('client_intent_id',))
        except ValueError:
            return _error(422, 'VALIDATION_ERROR', 'An exact session scope and interrupt intent are required.')
        intent = request.query_params['client_intent_id']
        if not 1 <= len(intent) <= 160 or not intent.isprintable():
            return _error(422, 'VALIDATION_ERROR', 'The interrupt intent is invalid.')
        state = request.app.state
        auth = state.operator_auth

        def read():
            ref = auth.authority_reference(request.cookies.get(COOKIE), create=False)
            if ref is None:
                raise OktoNexusError(ErrorCode.NOT_FOUND, 'The interrupt receipt was not found in this scope.')
            return read_human_interrupt_receipt(state.deps.connection_factory, access=build_execution_access(state.deps),
                resolve_human=auth.resolve_authority, scope=scope, author=InputAuthor(ref, surface), client_intent_id=intent,
                current_interrupt_target=_interrupt_target_for(state))

        try:
            return JSONResponse(await anyio.to_thread.run_sync(read), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.get('/interrupt/receipt')
    async def interrupt_receipt(session_id: str, request: Request):
        return await interrupt_receipt_for(session_id, request, 'web')

    @router.get('/terminal/interrupt/receipt')
    async def terminal_interrupt_receipt(session_id: str, request: Request):
        return await interrupt_receipt_for(session_id, request, 'nexus_cli')

    @router.get('/presenter/interrupt/receipt')
    async def presenter_interrupt_receipt(session_id: str, request: Request):
        return await interrupt_receipt_for(session_id, request, 'native_terminal')

    return router


def _runtime_error(error):
    status = {ErrorCode.NOT_FOUND: 404, ErrorCode.PERMISSION_DENIED: 403, ErrorCode.CONFLICT: 409,
              ErrorCode.VALIDATION_ERROR: 422}.get(error.code, 500)
    if status == 500:
        return _error(status, 'INTERNAL', 'Session interaction is temporarily unavailable.')
    return _error(status, error.code, error.message)
