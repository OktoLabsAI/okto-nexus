"""SSE event feed: GET /api/v1/stream (spec S1, C7 / FR6).

Anchored on the append-only ``events`` table: ``event_id`` is the SSE ``id``,
so a reconnecting client sends ``Last-Event-ID`` and resumes exactly after
its cursor - no loss, no duplication (rule br_ea308c93). Publication is the
bounded 1s poll from TR7 (the in-process push notifier is the F4 Waiter
upgrade); a comment ping every 15s keeps idle proxies from dropping the
connection.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import anyio.to_thread
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

#: Page size per poll round; a burst larger than this drains across rounds.
FETCH_LIMIT = 500


def _parse_cursor(request: Request) -> int:
    raw = request.headers.get("last-event-id") or request.query_params.get(
        "last_event_id", "0"
    )
    try:
        return max(0, int(str(raw).strip()))
    except (TypeError, ValueError):
        return 0


def _format_event(row: dict) -> str:
    payload = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
    return f"id: {row['event_id']}\nevent: nexus\ndata: {payload}\n\n"


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/stream")
    async def stream_events(
        request: Request,
        workspace: str | None = None,
        stream: str | None = None,
    ) -> StreamingResponse:
        deps = request.app.state.deps
        observability = request.app.state.observability
        poll_seconds: float = request.app.state.sse_poll_seconds
        ping_seconds: float = request.app.state.sse_ping_seconds
        cursor = _parse_cursor(request)

        def _fetch(after: int) -> list[dict]:
            # Read-only SSE poll: a DEFERRED WAL snapshot (write=False) so this
            # continuous loop never takes the write lock and never queues the
            # dashboard behind the agents' writers (the stall root cause).
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return observability.events_page(
                    uow,
                    cursor=after,
                    workspace_id=workspace,
                    stream=stream,
                    limit=FETCH_LIMIT,
                )

        async def generator() -> AsyncIterator[str]:
            # Client disconnect surfaces as task cancellation inside the
            # sleep/fetch awaits (StreamingResponse cancels the generator);
            # polling request.is_disconnected() here can block on the
            # exhausted receive channel under the test client.
            nonlocal cursor
            # Server shutdown is the OTHER exit: the client stays connected, so
            # nothing cancels this generator. uvicorn flips ``should_exit`` the
            # instant CTRL+C is pressed (before the graceful-shutdown wait), so
            # breaking on it lets this otherwise-infinite feed end on its own
            # instead of wedging shutdown. Absent under the test client (no
            # uvicorn server on app.state) -> falls back to client-cancel only.
            server = getattr(request.app.state, "server", None)
            since_ping = 0.0
            # Resume pass first: everything already written past the cursor
            # flushes immediately on connect (AC6).
            while True:
                if server is not None and server.should_exit:
                    break
                rows = await anyio.to_thread.run_sync(_fetch, cursor)
                if rows:
                    for row in rows:
                        cursor = row["event_id"]
                        yield _format_event(row)
                    since_ping = 0.0
                    continue  # drain bursts back-to-back, no sleep between pages
                await asyncio.sleep(poll_seconds)
                since_ping += poll_seconds
                if since_ping >= ping_seconds:
                    since_ping = 0.0
                    yield ": ping\n\n"

        return StreamingResponse(
            generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return router
