"""Attention uses the existing SSE endpoint as a bounded invalidation feed."""
import asyncio
import json
import sqlite3

import anyio.to_thread
from fastapi.responses import StreamingResponse

from ....errors import ErrorCode, OktoNexusError
from .identity_ctx import runtime_request_context
from .operator_auth import COOKIE
from .routes import _err, _map_error


def _control(event, *, cursor, reason, clear=False):
    value = dict(version=1, event_cursor=cursor, reason=reason, clear=clear)
    return f'id: {cursor}\nevent: {event}\ndata: {json.dumps(value, separators=(",", ":"))}\n\n'


def _gap(after, latest, earliest):
    return after > latest or (earliest is not None and after < earliest - 1
                              or earliest is None and after < latest)


async def attention_stream(request, *, cursor, workspace=None, stream=None):
    deps, attention = request.app.state.deps, request.app.state.attention
    context = runtime_request_context()

    def fetch(after=None):
        try:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                attention._authorize(uow, context)
                bounds = uow.connection.execute("SELECT COALESCE((SELECT seq FROM sqlite_sequence WHERE name='events'),0),"
                                                '(SELECT MIN(event_id) FROM events)').fetchone()
                latest, earliest = int(bounds[0]), bounds[1]
                gap = after is not None and _gap(after, latest, earliest)
                rows = []
                if after is not None and not gap:
                    rows = request.app.state.observability.events_page(
                        uow, cursor=after, workspace_id=workspace, stream=stream, limit=500)
                return rows, latest, gap
        except sqlite3.Error:
            raise OktoNexusError(ErrorCode.DB_ERROR,
                'The attention source is temporarily unavailable. Refresh the snapshot.', {}) from None

    try:
        _, initial_cursor, initial_gap = await anyio.to_thread.run_sync(fetch, cursor)
    except OktoNexusError as error:
        response = (_err(409, error.code, error.message) if error.code == 'FEATURE_DISABLED' else _map_error(error))
        response.headers['Cache-Control'] = 'no-store'
        return response

    async def generate():
        current = initial_cursor
        # Every connection starts a new canonical snapshot, then follows later
        # invalidations. It never replays historical notification bodies/toasts.
        yield _control('attention-reset', cursor=current,
                       reason='retention_gap' if initial_gap else 'snapshot_required')
        since_ping = 0.0
        poll = request.app.state.sse_poll_seconds
        while True:
            server = getattr(request.app.state, 'server', None)
            if server is not None and server.should_exit:
                return
            if getattr(request.state, 'operator_session', False):
                try:
                    authorized = await anyio.to_thread.run_sync(request.app.state.operator_auth.resolve,
                                                                request.cookies.get(COOKIE))
                except sqlite3.Error:
                    yield _control('attention-reset', cursor=current, reason='source_unavailable')
                    return
                if not authorized:
                    yield _control('attention-reset', cursor=current, reason='authorization_lost', clear=True)
                    return
            try:
                rows, latest, gap = await anyio.to_thread.run_sync(fetch, current)
            except OktoNexusError as error:
                clear = error.code in {ErrorCode.PERMISSION_DENIED, 'FEATURE_DISABLED'}
                reason = 'feature_disabled' if error.code == 'FEATURE_DISABLED' else 'authorization_lost' if clear else 'source_unavailable'
                yield _control('attention-reset', cursor=current, reason=reason, clear=clear)
                return
            if gap:
                current = latest
                yield _control('attention-reset', cursor=current, reason='retention_gap')
            elif rows:
                current = rows[-1]['event_id']
                # One metadata-only invalidation per batch, never token bodies.
                yield _control('attention-invalidated', cursor=current, reason='canonical_change')
            elif latest > current:
                # Other workspaces/streams do not hold this filtered follower
                # behind the global retention boundary.
                current = latest
            await asyncio.sleep(poll)
            since_ping += poll
            if since_ping >= request.app.state.sse_ping_seconds:
                since_ping = 0
                yield ': ping\n\n'

    return StreamingResponse(generate(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'})
