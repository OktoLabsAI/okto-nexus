"""Notify a dashboard conversation when the exact committed cursor changes."""

import asyncio
import json
from dataclasses import asdict

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ....bootstrap.execution_authority import build_execution_access
from ....errors import ErrorCode, OktoNexusError
from .dashboard_session_input import (
    _HEADERS,
    _error,
    _exact_view,
    _read_scope,
    _runtime_error,
)
from .identity_ctx import get_authenticated_agent, runtime_request_context
from .operator_auth import COOKIE


def _encode(event, document):
    return f'event: {event}\ndata: {json.dumps(document, separators=(",", ":"))}\n\n'


def read_conversation_position(factory, *, access, context, document, scope):
    """Read metadata and authorization from the same committed snapshot."""
    with factory.unit_of_work(write=False) as uow:
        exact = _exact_view(factory, uow, context=context, access=access, document=document, scope=scope)
        position = uow.connection.execute("""
            SELECT s.stream_epoch, COALESCE(w.committed_contiguous, 0) AS committed_contiguous,
                   COALESCE(w.gap_state, 'none') <> 'none' AS gap_pending
            FROM execution_sessions s
            LEFT JOIN execution_event_watermarks w USING (server_id, executor_id, session_id, stream_epoch)
            WHERE s.server_id=:server_id AND s.executor_id=:executor_id AND s.session_id=:session_id
        """, asdict(scope.session)).fetchone()
        return {'version': 1, 'scope': exact, **dict(position), 'gap_pending': bool(position['gap_pending'])}


async def _follow(request, read, initial):
    state = request.app.state
    server = getattr(state, 'server', None)
    interval = state.sse_poll_seconds
    ping = state.sse_ping_seconds
    signed_in = getattr(request.state, 'operator_session', False)
    token = request.cookies.get(COOKIE)
    previous = None
    waiting = 0.0

    while server is None or not server.should_exit:
        if signed_in and not await anyio.to_thread.run_sync(state.operator_auth.resolve, token):
            yield _encode('conversation-unavailable', {'version': 1, 'reason': 'authorization_lost'})
            return
        try:
            current = initial if previous is None else await anyio.to_thread.run_sync(read)
        except OktoNexusError as error:
            reason = {ErrorCode.PERMISSION_DENIED: 'authorization_lost', ErrorCode.NOT_FOUND: 'scope_changed'}.get(
                error.code, 'temporarily_unavailable')
            yield _encode('conversation-unavailable', {'version': 1, 'reason': reason})
            return
        if current != previous:
            yield _encode('conversation-position', current)
            previous = current
            waiting = 0.0
        else:
            waiting += interval
            if waiting >= ping:
                yield ': ping\n\n'
                waiting = 0.0
        await asyncio.sleep(interval)


def build_router():
    router = APIRouter(prefix='/runtime/sessions/{session_id}')

    @router.get('/conversation/stream')
    async def conversation_stream(session_id: str, request: Request):
        if get_authenticated_agent() is None:
            return _error(401, 'AUTH_FAILED', 'Authentication is required.')
        try:
            document, scope = _read_scope(request, session_id)
        except ValueError:
            return _error(422, 'VALIDATION_ERROR', 'An exact session scope is required.')
        deps = request.app.state.deps
        context = runtime_request_context()
        access = build_execution_access(deps)

        def read():
            return read_conversation_position(deps.connection_factory, access=access,
                                              context=context, document=document, scope=scope)

        try:
            initial = await anyio.to_thread.run_sync(read)
        except OktoNexusError as error:
            return _runtime_error(error)
        return StreamingResponse(_follow(request, read, initial), media_type='text/event-stream',
                                 headers={**_HEADERS, 'X-Accel-Buffering': 'no'})

    return router
