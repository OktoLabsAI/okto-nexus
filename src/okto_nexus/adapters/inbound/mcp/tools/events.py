"""MCP inbound tools for the Event Log slice.

Registers the two tools this slice owns exclusively, each returning the
canonical envelope via :func:`tool_envelope` so no exception ever crosses the
adapter boundary:

* ``event_get``  - non-blocking, cursor-paginated read of the workspace log.
* ``event_wait`` - snapshot by default (``timeout_seconds`` defaults to 0);
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

import os
from typing import Annotated, Any, Mapping

from pydantic import Field

from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.application.events import (
    DEFAULT_EVENT_LIMIT,
    MAX_EVENT_LIMIT,
    EventService,
)
from okto_nexus.envelope import tool_envelope

#: Reused parameter descriptions (kept DRY across the two event tools).
#: House style (mirrors okto-pulse): enums as "one of: a, b, c (default: x)";
#: optionals marked "(optional)"/"(default: ...)"; cross-refs to sibling tools.
_P_ROOT = "Absolute path to the project; the server derives workspace_id = sha256(realpath)."
_P_AGENT = "Your agent_id; scopes per-event visibility (you only see events you may see)."
_P_STREAM = (
    "Event stream to read - one of: workspace, agent, task, handoff. "
    "message.created and artifact.created are published on workspace."
)
_P_CURSOR = (
    "Pagination cursor: the last event_id you consumed; the scan returns "
    "event_id > cursor (optional; omit or 0 to start from the beginning)."
)
_P_LIMIT = "Max events per page (optional; default 100, clamped to the server maximum, default 1000)."
_P_FILTERS = (
    "Equality filters, AND-combined (optional). Allowed keys: type, agent_id, "
    'task_id, handoff_id (e.g. {"type": "message.created"}).'
)
_P_TIMEOUT = (
    "Long-poll bound in SECONDS (optional; default 0). 0, OMITTED or null is an "
    "immediate non-blocking snapshot (single scan, no sleep). >0 OPTS IN to a "
    "BLOCKING long-poll: it parks your turn until an event arrives or the "
    "timeout elapses (clamped to the server max wait) - see the server "
    "instructions before blocking."
)

#: Environment knob for the maximum page size (``limit`` ceiling). Not part of
#: ``NexusConfig``, so it is resolved here in the inbound adapter.
MAX_EVENT_LIMIT_ENV = "OKTO_NEXUS_MAX_EVENT_LIMIT"


def _resolve_max_limit(env: Mapping[str, str]) -> int:
    """Resolve the page-size ceiling from the environment (positive int)."""
    raw = env.get(MAX_EVENT_LIMIT_ENV)
    if raw is None or not str(raw).strip():
        return MAX_EVENT_LIMIT
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return MAX_EVENT_LIMIT
    return value if value > 0 else MAX_EVENT_LIMIT


def build_service(deps: Any, env: Mapping[str, str] | None = None) -> EventService:
    """Wire the SQLite repos/emitter into ``deps`` and build the service.

    Idempotent: an event repo / emitter / agents repo already present is reused
    so this slice and its peers share a single concrete instance and a single
    append path.
    """
    environ = env if env is not None else os.environ
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
        max_limit=_resolve_max_limit(environ),
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
    def event_wait(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        stream: Annotated[str, Field(description=_P_STREAM)],
        cursor: Annotated[Any, Field(description=_P_CURSOR)] = None,
        limit: Annotated[Any, Field(description=_P_LIMIT)] = None,
        filters: Annotated[Any, Field(description=_P_FILTERS)] = None,
        timeout_seconds: Annotated[Any, Field(description=_P_TIMEOUT)] = 0,
    ) -> dict[str, Any]:
        """Read the event log; optionally long-poll until a non-empty page.

        SAFE BY DEFAULT: ``timeout_seconds`` omitted, ``0`` or ``null`` is an
        immediate NON-BLOCKING snapshot (single scan, no sleep) - the same
        default as ``handoff_list_available``. Blocking is an explicit opt-in:
        with ``timeout_seconds > 0`` the call parks the caller's turn until an
        event arrives or the timeout expires (clamped to the server ceiling).
        Pick a mode so a single-threaded harness is never forced to block:
          * Background follower (best): spawn a detached ``okto-nexus tail``
            (or an event_wait loop) and react to each emitted NDJSON line; the
            agent loop stays free, idle cost ~0.
          * In-loop, no background: keep the default snapshot; poll between
            turns, advancing ``cursor`` -> ``next_cursor``.
          * Targeted wait: a short ``timeout_seconds > 0`` to await an
            expected event.
        The block is inherent to the current stdio long-poll; the planned
        SSE/HTTP transport would replace it with server push.
        """
        # Safe-by-default: an omitted/null timeout is a snapshot; the
        # application layer would treat None as "use the server ceiling".
        return service.event_wait(
            project_root=project_root,
            agent_id=agent_id,
            stream=stream,
            cursor=cursor,
            limit=limit,
            filters=filters,
            timeout_seconds=0 if timeout_seconds is None else timeout_seconds,
        )
