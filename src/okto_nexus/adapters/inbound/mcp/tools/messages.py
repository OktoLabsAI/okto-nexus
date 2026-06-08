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


def build_service(deps: Any) -> MessageService:
    """Wire the SQLite repos/emitter into ``deps`` and build the service.

    Idempotent: any repo / emitter already present is reused so this slice and
    its peers share a single concrete instance and a single event append path.
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
    def channel_list(project_root: str) -> dict[str, Any]:
        """Return the per-workspace seeded channels."""
        return service.list_channels(project_root=project_root)
