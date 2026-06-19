"""MCP inbound tools for the Event Log slice.

Registers the two tools this slice owns exclusively, each returning the
canonical envelope via :func:`tool_envelope` so no exception ever crosses the
adapter boundary:

* ``event_get``    - non-blocking, cursor-paginated read of the workspace log.
* ``event_cursor`` - O(1) end-of-stream position (the pre-flight monitor anchor).
* ``event_wait``   - snapshot by default (``timeout_seconds`` defaults to 0);
  passing ``timeout_seconds > 0`` OPTS IN to a blocking long-poll
  (``event_get`` + poll/sleep loop) bounded by the configured timeout ceiling.

Pagination/filter parameters (``cursor``/``limit``/``filters``/
``timeout_seconds``) are deliberately annotated ``Any``: the application layer
validates them and a wrong type comes back as the canonical
``VALIDATION_ERROR`` envelope instead of a FastMCP/pydantic validation error
(one error grammar for agents).

This module is the slice's composition root: it wires the concrete SQLite
:class:`SqliteEventRepo` into ``deps.repos.events`` and publishes the
:class:`SqliteEventEmitter` on ``deps.event_emitter`` (only if not already
provided) so peer slices emit their audit events through the same append path.
It also makes the agents repo available (for visibility resolution). It does NOT
import the MCP SDK; the live FastMCP server is passed into :func:`register`,
matching the ``register(server, deps)`` contract.
"""

from __future__ import annotations

import functools
from typing import Annotated, Any

import anyio.to_thread
from pydantic import Field

from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.application.events import (
    DEFAULT_EVENT_LIMIT,
    EventService,
)
from okto_nexus.envelope import async_tool_envelope, tool_envelope

#: Reused parameter descriptions (kept DRY across the two event tools).
#: House style (mirrors okto-pulse): enums as "one of: a, b, c (default: x)";
#: optionals marked "(optional)"/"(default: ...)"; cross-refs to sibling tools.
_P_ROOT = "Absolute path to the project; the server derives workspace_id = sha256(realpath)."
_P_AGENT = "Your agent_id; scopes per-event visibility (you only see events you may see)."
_P_STREAM = "Event stream to read - one of: workspace, agent, handoff. message.created, the message.delivered/message.read receipts and artifact.created are on workspace."
_P_CURSOR = "Pagination cursor: the last event_id you consumed; returns event_id > cursor (optional; omit/0 = from the beginning)."
_P_LIMIT = "Max events per page (optional; default 100, clamped to the server maximum, default 1000)."
_P_FILTERS = (
    "Equality filters, AND-combined (optional). Keys: type, agent_id, task_id, "
    'handoff_id. e.g. {"type":"message.created"}.'
)
_P_TIMEOUT = (
    "Long-poll bound in SECONDS (optional; default 0). 0/omitted/null = an "
    "immediate non-blocking snapshot; >0 OPTS IN to a BLOCKING long-poll until an "
    "event arrives or the timeout elapses. Listener patterns: okto-nexus://reference/monitoring."
)

def build_service(deps: Any) -> EventService:
    """Wire the SQLite repos/emitter into ``deps`` and build the service.

    Idempotent: an event repo / emitter / agents repo already present is reused
    so this slice and its peers share a single concrete instance and a single
    append path. The page-size ceiling comes from
    ``deps.config.max_event_limit`` (env ``OKTO_NEXUS_MAX_EVENT_LIMIT`` /
    ``--max-event-limit``, parsed FAIL-CLOSED by ``load_config`` - an invalid
    value aborts startup with CONFIG_ERROR instead of silently falling back).
    """
    repos = deps.repos

    if getattr(repos, "events", None) is None:
        repos.events = SqliteEventRepo(deps.clock)
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)
    if getattr(deps, "event_emitter", None) is None:
        deps.event_emitter = SqliteEventEmitter(repos.events)

    return EventService(
        connection_factory=deps.connection_factory,
        events=repos.events,
        agents=repos.agents,
        clock=deps.clock,
        config=deps.config,
        default_limit=DEFAULT_EVENT_LIMIT,
        max_limit=deps.config.max_event_limit,
    )


def register(server: Any, deps: Any) -> None:
    """Register the event tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def event_get(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        stream: Annotated[str, Field(description=_P_STREAM)],
        cursor: Annotated[Any, Field(description=_P_CURSOR)] = None,
        limit: Annotated[Any, Field(description=_P_LIMIT)] = None,
        filters: Annotated[Any, Field(description=_P_FILTERS)] = None,
    ) -> dict[str, Any]:
        """Read a cursor-paginated page of the workspace event log (non-blocking)."""
        return service.event_get(
            project_root=project_root,
            agent_id=agent_id,
            stream=stream,
            cursor=cursor,
            limit=limit,
            filters=filters,
        )

    @server.tool()
    @tool_envelope
    def event_cursor(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        stream: Annotated[str, Field(description=_P_STREAM)],
    ) -> dict[str, Any]:
        """Return the stream's CURRENT END as a cursor (O(1), no scan) - the pre-flight monitor anchor so you see only events appended after now. Returns {cursor} (0 for empty)."""
        return {
            "cursor": service.latest_cursor(
                project_root=project_root, agent_id=agent_id, stream=stream
            )
        }

    @server.tool()
    @async_tool_envelope
    async def event_wait(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        stream: Annotated[str, Field(description=_P_STREAM)],
        cursor: Annotated[Any, Field(description=_P_CURSOR)] = None,
        limit: Annotated[Any, Field(description=_P_LIMIT)] = None,
        filters: Annotated[Any, Field(description=_P_FILTERS)] = None,
        timeout_seconds: Annotated[Any, Field(description=_P_TIMEOUT)] = 0,
    ) -> dict[str, Any]:
        """Read the event log; optionally long-poll (0/omitted/null = non-blocking snapshot; >0 OPTS IN to blocking). Events are observability, not delivery. Patterns: okto-nexus://reference/monitoring."""
        # Long-poll OFF the event loop: the blocking sleep-poll runs in a
        # worker thread so a parked event_wait never freezes the shared serve
        # event loop (which also drives the dashboard REST + every other MCP
        # tool over streamable-HTTP). Safe-by-default: an omitted/null timeout
        # is a snapshot; the application layer treats None as the server ceiling.
        return await anyio.to_thread.run_sync(
            functools.partial(
                service.event_wait,
                project_root=project_root,
                agent_id=agent_id,
                stream=stream,
                cursor=cursor,
                limit=limit,
                filters=filters,
                timeout_seconds=0 if timeout_seconds is None else timeout_seconds,
            )
        )
