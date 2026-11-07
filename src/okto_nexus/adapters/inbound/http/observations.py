"""Bounded external telemetry and separate canonical management endpoints."""
from functools import partial
import json

import anyio
from fastapi import APIRouter, Request

from ....errors import ErrorCode, OktoNexusError
from .identity_ctx import runtime_request_context
from .routes import _err, _map_error, _ok

MAX_REPORT_BYTES = 4096
MAX_BATCH_BYTES = 100 * MAX_REPORT_BYTES + 2048
MAX_MANAGEMENT_BYTES = 32768


def _invalid():
    raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid observation request.', {})


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _invalid()
        value[key] = item
    return value


async def _body(request, *, publish=False):
    if request.headers.get('content-encoding', 'identity') != 'identity':
        _invalid()
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        _invalid()
    maximum = MAX_BATCH_BYTES if publish else MAX_MANAGEMENT_BYTES
    content = bytearray()
    try:
        with anyio.fail_after(5):
            async for chunk in request.stream():
                if len(content) + len(chunk) > maximum:
                    raise OktoNexusError(ErrorCode.CONTENT_TOO_LARGE, 'The observation request is too large.', {})
                content.extend(chunk)
        value = json.loads(content.decode('utf-8'), object_pairs_hook=_object,
                           parse_constant=lambda _: _invalid())
    except (UnicodeError, ValueError, RecursionError, TimeoutError):
        _invalid()
    if publish and not (type(value) is dict and 'reports' in value) and len(content) > MAX_REPORT_BYTES:
        raise OktoNexusError(ErrorCode.CONTENT_TOO_LARGE, 'An observation exceeds 4 KiB.', {})
    return value


def _query(request, allowed):
    result = {}
    for key in request.query_params:
        if key not in allowed or len(request.query_params.getlist(key)) != 1:
            _invalid()
        value = request.query_params[key]
        if key == 'limit':
            if not value.isascii() or not value.isdecimal() or len(value) > 3:
                _invalid()
            value = int(value)
        result[key] = value
    return result


def _error(exc):
    if isinstance(exc, OktoNexusError):
        status = {'FEATURE_DISABLED': 409, 'OBSERVATION_BUSY': 503, 'OBSERVATION_QUERY_BUDGET': 503,
                  'OBSERVATION_CORRELATION_UNAVAILABLE': 503}.get(exc.code)
        response = (_err(status, exc.code, exc.message, exc.details) if status else _map_error(exc))
        if exc.code in ('OBSERVATION_BUSY', ErrorCode.QUOTA_EXCEEDED):
            response.headers['Retry-After'] = str(max(1, (exc.details or {}).get('retry_after_seconds', 1)))
        return response
    # Never expose raw SQLite/IO errors, bearer values, malformed JSON or caller
    # contents through the application's generic debug exception handler.
    return _err(503, 'OBSERVATION_UNAVAILABLE', 'Observation storage is unavailable.')


async def _call(request, method, *, body=False, query=frozenset(), **kwargs):
    service = request.app.state.observations
    try:
        values = _query(request, query)
        if request.method == 'GET':
            result = await anyio.to_thread.run_sync(partial(getattr(service, method),
                context=runtime_request_context(), **values, **kwargs))
        else:
            # Bound the queue before reading body or entering anyio's worker pool.
            with service.ingress.enter():
                if body:
                    kwargs['body'] = await _body(request)
                result = await anyio.to_thread.run_sync(partial(getattr(service, method),
                    context=runtime_request_context(), **values, **kwargs))
        response = _ok(result)
    except Exception as exc:
        response = _error(exc)
    response.headers['Cache-Control'] = 'no-store'
    return response


def management_router():
    router = APIRouter()

    @router.get('/observations')
    async def read(request: Request):
        return await _call(request, 'read', query={'agent_id', 'workspace_id', 'source_id', 'after', 'limit'})

    @router.get('/observations/summary')
    async def summary(request: Request):
        return await _call(request, 'summary', query={'agent_id', 'workspace_id', 'source_id'})

    @router.get('/observations/instances/{observed_instance_id}')
    async def instance(request: Request, observed_instance_id: str):
        return await _call(request, 'get_instance', observed_instance_id=observed_instance_id)

    @router.get('/observations/instances/{observed_instance_id}/correlation')
    @router.post('/observations/instances/{observed_instance_id}/correlation')
    @router.delete('/observations/instances/{observed_instance_id}/correlation')
    async def correlation(request: Request, observed_instance_id: str):
        try:
            _query(request, set())
            service = request.app.state.observation_correlations
            args = dict(context=runtime_request_context(), observed_instance_id=observed_instance_id)
            if request.method == 'GET':
                result = await anyio.to_thread.run_sync(partial(service.read, **args))
            else:
                with request.app.state.observations.ingress.enter():
                    args['body'] = await _body(request)
                    if request.method == 'POST':
                        result = await request.app.state.observation_correlation_proof.select(service, **args)
                    else:
                        result = await anyio.to_thread.run_sync(partial(service.clear, **args))
            response = _ok(result)
        except Exception as exc:
            response = _error(exc)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @router.get('/observations/sources')
    async def sources(request: Request):
        return await _call(request, 'list_sources', query={'agent_id', 'after', 'limit'})

    @router.post('/observations/sources')
    async def create_source(request: Request):
        return await _call(request, 'create_source', body=True)

    @router.get('/observations/sources/{source_id}')
    async def source(request: Request, source_id: str):
        return await _call(request, 'get_source', source_id=source_id)

    @router.patch('/observations/sources/{source_id}')
    async def update_source(request: Request, source_id: str):
        return await _call(request, 'update_source', source_id=source_id, body=True)

    @router.post('/observations/sources/{source_id}/revoke')
    async def revoke_source(request: Request, source_id: str):
        return await _call(request, 'revoke_source', source_id=source_id, body=True)

    @router.get('/observations/sources/{source_id}/instances')
    async def instances(request: Request, source_id: str):
        return await _call(request, 'list_instances', source_id=source_id, query={'after', 'limit'})

    @router.post('/observations/sources/{source_id}/instances')
    async def create_instance(request: Request, source_id: str):
        return await _call(request, 'create_instance', source_id=source_id, body=True)

    @router.post('/observations/sources/{source_id}/instances/{observed_instance_id}/rotate')
    async def rotate_instance(request: Request, source_id: str, observed_instance_id: str):
        return await _call(request, 'rotate_instance', source_id=source_id,
                           observed_instance_id=observed_instance_id, body=True)

    @router.post('/observations/sources/{source_id}/instances/{observed_instance_id}/retire')
    async def retire_instance(request: Request, source_id: str, observed_instance_id: str):
        return await _call(request, 'retire_instance', source_id=source_id,
                           observed_instance_id=observed_instance_id, body=True)

    @router.get('/observations/sources/{source_id}/tokens')
    async def tokens(request: Request, source_id: str):
        return await _call(request, 'list_tokens', source_id=source_id, query={'after', 'limit'})

    @router.post('/observations/sources/{source_id}/tokens')
    async def issue_token(request: Request, source_id: str):
        return await _call(request, 'issue_token', source_id=source_id, body=True)

    @router.post('/observations/sources/{source_id}/tokens/{token_id}/revoke')
    async def revoke_token(request: Request, source_id: str, token_id: str):
        return await _call(request, 'revoke_token', source_id=source_id, token_id=token_id)

    return router


def publish_router():
    router = APIRouter()

    @router.post('/observations/activity')
    async def publish(request: Request):
        try:
            _query(request, set())
            service = request.app.state.observations
            with service.ingress.enter():
                payload = await _body(request, publish=True)
                # Middleware requires the exact exclusive bearer audience; the
                # service revalidates the token's current facts inside its UoW.
                authorization = request.headers.get('authorization', '').split()
                token = authorization[1] if len(authorization) == 2 and authorization[0].lower() == 'bearer' else None
                result = await anyio.to_thread.run_sync(partial(service.publish, token=token, payload=payload))
            response = _ok(result)
        except Exception as exc:
            response = _error(exc)
        response.headers['Cache-Control'] = 'no-store'
        return response

    return router
