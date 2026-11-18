"""Dashboard interaction with one exact session under a real human login."""

from dataclasses import asdict
from functools import partial

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ....adapters.outbound.execution.core_inventory import protocol_info
from ....adapters.outbound.sqlite.session_interaction_queue_controls import (
    has_unresolved_interrupt,
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
from ....application.session_interaction_targets import active_native_turn
from ....bootstrap.execution_authority import build_execution_access
from ....domain.attention import digest
from ....domain.session_interaction import InputAuthor
from ....errors import ErrorCode, OktoNexusError
from .identity_ctx import get_authenticated_agent, runtime_request_context
from .operator_auth import COOKIE
from .session_interaction_contract import (
    CancelInput,
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
        possible_effect=receipt.possible_effect).model_dump(mode='json')


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
                epoch = uow.connection.execute(
                    'SELECT stream_epoch FROM execution_sessions WHERE server_id=? AND executor_id=? AND session_id=?',
                    (scope.session.server_id, scope.session.executor_id, session_id),
                ).fetchone()[0]
                revision = revision_for(uow, scope) if revision_for is not None else None
                return {'scope': exact, 'stream_epoch': epoch,
                        'next_turn': {'supported': revision is not None, 'capability_revision': revision,
                                      'human_login_required': not signed_in}}

        try:
            return JSONResponse(await anyio.to_thread.run_sync(read), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.post('/inputs', status_code=202)
    async def enqueue_input(session_id: str, body: EnqueueInput, request: Request):
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
                author=InputAuthor(reference, 'web'), client_intent_id=body.client_intent_id,
                capability_revision=body.capability_revision, text=body.content[0].text)
            return _receipt_document(body.scope, body.expected_session_generation, receipt)

        try:
            return JSONResponse(await anyio.to_thread.run_sync(submit), status_code=202, headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.get('/inputs/receipt')
    async def input_receipt(session_id: str, request: Request):
        if not getattr(request.state, 'operator_session', False):
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to recover a receipt.')
        try:
            document, scope = _read_scope(request, session_id, extra=('client_intent_id',))
        except ValueError:
            return _error(422, 'VALIDATION_ERROR', 'An exact session scope and message intent are required.')
        intent = request.query_params['client_intent_id']
        if not 1 <= len(intent) <= 160 or not intent.isprintable():
            return _error(422, 'VALIDATION_ERROR', 'The message intent is invalid.')
        state = request.app.state
        auth = state.operator_auth

        def read():
            ref = auth.authority_reference(request.cookies.get(COOKIE), create=False)
            if ref is None:
                raise OktoNexusError(ErrorCode.NOT_FOUND, 'The input receipt was not found in this scope.')
            receipt = read_session_input_receipt(state.deps.connection_factory, access=build_execution_access(state.deps),
                resolve_human=auth.resolve_authority, scope=scope, author=InputAuthor(ref, 'web'),
                client_intent_id=intent)
            return _receipt_document(document, scope.generation.value, receipt)

        try:
            return JSONResponse(await anyio.to_thread.run_sync(read), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

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
        next_turn = getattr(state, 'session_input_dispatch_options', {}).get('session_input_capability_revision')

        def read():
            with factory.unit_of_work(write=False) as uow:
                _exact_view(factory, uow, context=context, access=access, document=document, scope=scope)
                target = None
                if next_turn is not None and not has_unresolved_interrupt(uow.connection, scope.session):
                    target = active_native_turn(uow, scope, current_next_turn_revision=next_turn)
                control = None
                if target is not None:
                    row = uow.connection.execute("""
                        SELECT revision FROM session_interaction_queues
                        WHERE server_id=? AND executor_id=? AND session_id=?
                    """, (scope.session.server_id, scope.session.executor_id, session_id)).fetchone()
                    control = InterruptTargetView(
                        target=NativeTurnTarget(kind='native_turn', turn_id=target.native_id),
                        capability_revision=target.revision, queue_revision=row[0] if row else 0)
                return InterruptAvailability(scope=document, session_owner_generation=scope.generation.value,
                                             control=control).model_dump(mode='json')

        try:
            return JSONResponse(await anyio.to_thread.run_sync(read), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.post('/interrupt', status_code=202)
    async def interrupt(session_id: str, body: InterruptInput, request: Request):
        if not getattr(request.state, 'operator_session', False):
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to interrupt a turn.')
        if body.scope.session_id != session_id or request.query_params:
            return _error(422, 'VALIDATION_ERROR', 'The interrupt must use the exact session scope.')
        if not isinstance(body.target, NativeTurnTarget):
            return _error(409, 'CONFLICT', 'An exact native turn is required by this control.')
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
                current_interrupt_revision=options['session_interrupt_capability_revision'], scope=body.input_scope(),
                author=InputAuthor(ref, 'web'), client_intent_id=body.client_intent_id, native_turn_id=body.target.turn_id,
                capability_revision=body.capability_revision, expected_queue_revision=body.expected_queue_revision,
                fresh_publications=state.inventory_fresh_publications, remote_ready=protocol_info()['remote_execution_ready'])

        try:
            operation, reused = await anyio.to_thread.run_sync(admit)
            return JSONResponse(operation, status_code=200 if reused else 202, headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    @router.get('/interrupt/receipt')
    async def interrupt_receipt(session_id: str, request: Request):
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
                resolve_human=auth.resolve_authority, scope=scope, author=InputAuthor(ref, 'web'), client_intent_id=intent)

        try:
            return JSONResponse(await anyio.to_thread.run_sync(read), headers=_HEADERS)
        except OktoNexusError as error:
            return _runtime_error(error)

    return router


def _runtime_error(error):
    status = {ErrorCode.NOT_FOUND: 404, ErrorCode.PERMISSION_DENIED: 403, ErrorCode.CONFLICT: 409,
              ErrorCode.VALIDATION_ERROR: 422}.get(error.code, 500)
    if status == 500:
        return _error(status, 'INTERNAL', 'Session interaction is temporarily unavailable.')
    return _error(status, error.code, error.message)
