"""Dashboard admission of one native next-turn input by a real human login."""

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ....application.execution_session_views import read_execution_session
from ....application.session_interaction_authority import enqueue_human_input
from ....application.session_interaction_receipts import read_session_input_receipt
from ....bootstrap.execution_authority import build_execution_access
from ....domain.session_interaction import InputAuthor
from ....errors import ErrorCode, OktoNexusError
from .identity_ctx import get_authenticated_agent, runtime_request_context
from .operator_auth import COOKIE
from .session_interaction_contract import EnqueueInput, ExactSessionScope, InputReceipt

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
                view = read_execution_session(factory, server_id=scope.session.server_id,
                    executor_id=scope.session.executor_id, session_id=session_id, context=context, access=access, _uow=uow)
                exact = {**document.model_dump(), 'session_owner_generation': scope.generation.value}
                if any(view['scope'][key] != value for key, value in exact.items()):
                    raise OktoNexusError(ErrorCode.NOT_FOUND, 'The session is outside this scope.')
                revision = revision_for(uow, scope) if revision_for is not None else None
                return {'scope': exact,
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

    return router


def _runtime_error(error):
    status = {ErrorCode.NOT_FOUND: 404, ErrorCode.PERMISSION_DENIED: 403, ErrorCode.CONFLICT: 409,
              ErrorCode.VALIDATION_ERROR: 422}.get(error.code, 500)
    if status == 500:
        return _error(status, 'INTERNAL', 'Session interaction is temporarily unavailable.')
    return _error(status, error.code, error.message)
