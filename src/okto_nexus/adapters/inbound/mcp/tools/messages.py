"""MCP inbound tools for the Channels & Messages slice.

Registers the four tools this slice owns exclusively, each returning the
canonical envelope via :func:`tool_envelope` so no exception ever crosses the
adapter boundary:

* ``message_create`` - persist a message + emit ``message.created`` atomically.
* ``message_get``    - workspace-scoped single read (visibility-filtered).
* ``message_list``   - event-ordered, cursor-paginated, visibility-filtered list.
* ``channel_list``   - the per-workspace seeded channels.

This module is the slice's composition root: it wires the concrete SQLite
:class:`SqliteChannelRepo` / :class:`SqliteMessageRepo` into ``deps.repos`` and
reuses (or lazily wires) the peer-owned workspace/agent repos and the Event Log
``EventEmitter`` so ``message.created`` flows through the same append path. It
does NOT import the MCP SDK; the live FastMCP server is passed into
:func:`register`, matching the ``register(server, deps)`` contract.
"""

from __future__ import annotations

from typing import Any

from okto_nexus.adapters.outbound.sqlite.events_repo import (
    SqliteEventEmitter,
    SqliteEventRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import (
    SqliteAgentRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteChannelRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.messages import MessageService
from okto_nexus.envelope import tool_envelope

from .events import build_service as build_event_service


def build_service(deps: Any) -> MessageService:
    """Wire the SQLite repos/emitter into ``deps`` and build the service.

    Idempotent: any repo / emitter already present is reused so this slice and
    its peers share a single concrete instance and a single event append path.
    The Event Log :class:`EventService` is built (reusing the same wired repos)
    and injected as the :class:`EventWaiter`, so ``message_wait`` reuses the one
    long-poll implementation instead of duplicating the poll/sleep loop.
    """
    repos = deps.repos

    if getattr(repos, "channels", None) is None:
        repos.channels = SqliteChannelRepo(deps.clock)
    if getattr(repos, "messages", None) is None:
        repos.messages = SqliteMessageRepo(deps.clock)
    if getattr(repos, "workspaces", None) is None:
        repos.workspaces = SqliteWorkspaceRepo(deps.clock)
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)
    if getattr(deps, "event_emitter", None) is None:
        if getattr(repos, "events", None) is None:
            repos.events = SqliteEventRepo(deps.clock)
        deps.event_emitter = SqliteEventEmitter(repos.events)

    return MessageService(
        connection_factory=deps.connection_factory,
        channels=repos.channels,
        messages=repos.messages,
        workspaces=repos.workspaces,
        agents=repos.agents,
        event_emitter=deps.event_emitter,
        clock=deps.clock,
        max_inline_bytes=deps.config.max_inline_bytes,
        event_waiter=build_event_service(deps),
    )


def register(server: Any, deps: Any) -> None:
    """Register the message/channel tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def message_create(
        project_root: str,
        from_agent_id: str,
        subject: str,
        body: str,
        channel_id: str | None = None,
        from_session_id: str | None = None,
        target: dict[str, Any] | None = None,
        artifacts: list[str] | None = None,
        parent_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist a message and emit ``message.created`` in one transaction."""
        return service.create_message(
            project_root=project_root,
            from_agent_id=from_agent_id,
            subject=subject,
            body=body,
            channel_id=channel_id,
            from_session_id=from_session_id,
            target=target,
            artifacts=artifacts,
            parent_message_id=parent_message_id,
        )

    @server.tool()
    @tool_envelope
    def message_get(
        project_root: str,
        message_id: str,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Read a single workspace-scoped, visibility-filtered message."""
        return service.get_message(
            project_root=project_root,
            message_id=message_id,
            viewer_agent_id=agent_id,
        )

    @server.tool()
    @tool_envelope
    def message_list(
        project_root: str,
        channel_id: str | None = None,
        cursor: int | None = None,
        limit: int | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """List workspace messages ordered by event_id with cursor pagination."""
        return service.list_messages(
            project_root=project_root,
            channel_id=channel_id,
            cursor=cursor,
            limit=limit,
            viewer_agent_id=agent_id,
        )

    @server.tool()
    @tool_envelope
    def message_wait(
        project_root: str,
        agent_id: str,
        channel_id: str | None = None,
        cursor: int | None = None,
        limit: int | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Long-poll for new messages, returning them materialised with body.

        Reuses ``event_wait`` under the hood and resolves each ``message.created``
        into a full, visibility-filtered message (collapsing
        event_wait -> parse -> message_get into one call). ``cursor`` is the
        event_id cursor; ``next_cursor`` advances as with ``event_wait``.

        CONCURRENCY - this is a BLOCKING long-poll: with ``timeout_seconds > 0``
        it parks the caller's turn until a message arrives or the timeout
        expires. Pick a mode so a single-threaded harness is never forced to
        block:
          * Background follower (best): if you can spawn a detached process, run
            ``okto-nexus tail --from latest`` (or a message_wait loop) in the
            background and treat each emitted line as a notification - the agent
            loop stays free, idle cost ~0. The layer-clean replacement for
            reading the DB directly.
          * In-loop, no background: call with ``timeout_seconds=0`` for a
            NON-BLOCKING snapshot (single scan, no sleep) and poll between turns,
            advancing ``cursor`` -> ``next_cursor``.
          * Targeted wait: a short ``timeout_seconds`` (e.g. 30) is fine to await
            the reply to a message you just sent, accepting the block.
        The block is inherent to the current stdio long-poll; the planned
        SSE/HTTP transport would remove it (server push, no blocking/polling).
        """
        return service.wait_messages(
            project_root=project_root,
            agent_id=agent_id,
            channel_id=channel_id,
            cursor=cursor,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )

    @server.tool()
    @tool_envelope
    def channel_list(project_root: str) -> dict[str, Any]:
        """Return the per-workspace seeded channels."""
        return service.list_channels(project_root=project_root)
