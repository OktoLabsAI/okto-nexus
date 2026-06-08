"""MCP inbound tools for the Event Log slice.

Registers the two tools this slice owns exclusively, each returning the
canonical envelope via :func:`tool_envelope` so no exception ever crosses the
adapter boundary:

* ``event_get``  - non-blocking, cursor-paginated read of the workspace log.
* ``event_wait`` - long-poll (``event_get`` + poll/sleep loop) bounded by the
  configured timeout ceiling.

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
from typing import Any, Mapping

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
        project_root: str,
        agent_id: str,
        stream: str,
        cursor: int | None = None,
        limit: int | None = None,
        filters: dict[str, Any] | None = None,
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
        project_root: str,
        agent_id: str,
        stream: str,
        cursor: int | None = None,
        limit: int | None = None,
        filters: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Long-poll the event log until a non-empty page or the timeout ceiling."""
        return service.event_wait(
            project_root=project_root,
            agent_id=agent_id,
            stream=stream,
            cursor=cursor,
            limit=limit,
            filters=filters,
            timeout_seconds=timeout_seconds,
        )
