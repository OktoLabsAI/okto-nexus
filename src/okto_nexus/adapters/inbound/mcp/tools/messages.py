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

from typing import Annotated, Any

from pydantic import Field

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

#: Reused parameter descriptions (kept DRY across the message/channel tools).
#: House style (mirrors okto-pulse): enums as "one of: a, b, c (default: x)";
#: optionals marked "(optional)"/"(default: ...)"; cross-refs to sibling tools.
_P_ROOT = "Absolute path to the project; the server derives workspace_id = sha256(realpath)."
_P_FROM_AGENT = "Your agent_id (the sender); recorded as the author - recipients reply by targeting it."
_P_SUBJECT = "Short message subject/title (one line)."
_P_BODY = (
    "Message body (inline text). For large content, attach an artifact via "
    "artifacts and keep the body a short pointer instead of inlining it."
)
_P_CHANNEL = (
    "Channel_id to post into (optional; omit to post to the workspace default "
    "channel). Enumerate channels with channel_list."
)
_P_FROM_SESSION = "Session_id attributing the message to a specific open session of yours (optional)."
#: The routing target controls FAN-OUT/visibility for messages (pub/sub: every
#: eligible agent receives it). Spell out the ``strategy`` enum and each shape.
_P_TARGET_MSG = (
    "Routing rule selecting who receives this message (optional; omit for "
    "broadcast to the whole workspace). A message is pub/sub - every eligible "
    "agent receives it; to reply 1:1 use direct. strategy is one of: direct, "
    "capability, role, broadcast, mixed, direct_with_fallback. Shapes: "
    'direct {"strategy":"direct","agent_id":"<id>"}; '
    'capability {"strategy":"capability","capability":"<cap>"} (string or list = any-of); '
    'role {"strategy":"role","role":"<role>"} (exact, case-sensitive); '
    'broadcast {"strategy":"broadcast"}; '
    'mixed {"strategy":"mixed","rules":[<sub-target>, ...]} (OR of sub-targets); '
    'direct_with_fallback {"strategy":"direct_with_fallback","agent_id":"<id>",'
    '"fallback_after_seconds":<n>,"fallback":<sub-target, default broadcast>}.'
)
_P_ARTIFACTS = (
    "List of artifact_id strings to attach (optional; reference large content "
    "instead of inlining it in body)."
)
_P_PARENT = "Message_id this is a reply to, to thread the conversation (optional)."
_P_MESSAGE_ID = "The message_id to read. REQUIRED."
_P_VIEWER_OPT = (
    "Your agent_id as the visibility viewer - you only see messages you are "
    "allowed to see (optional). Omit for an UNFILTERED admin read that also "
    "returns messages directed at other agents; pass your agent_id for the normal "
    "scoped view."
)
_P_CURSOR = (
    "Pagination cursor: the last event_id you consumed; returns event_id > cursor "
    "(optional; omit or 0 to start from the beginning)."
)
_P_LIMIT = "Max messages per page (optional; default applied by the server, clamped to the maximum)."
_P_WAIT_AGENT = "Your agent_id - the visibility viewer and the inbox you long-poll for. REQUIRED."
_P_TIMEOUT = (
    "Long-poll bound in SECONDS (optional). >0 blocks until a message arrives or "
    "the timeout elapses; 0 is a single non-blocking scan (no sleep); OMITTED "
    "defaults to the server max wait - the longest blocking poll, NOT a snapshot. "
    "Clamped to the server max wait. BLOCKING: parks your turn - see the server "
    "instructions."
)


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
        project_root: Annotated[str, Field(description=_P_ROOT)],
        from_agent_id: Annotated[str, Field(description=_P_FROM_AGENT)],
        subject: Annotated[str, Field(description=_P_SUBJECT)],
        body: Annotated[str, Field(description=_P_BODY)],
        channel_id: Annotated[str | None, Field(description=_P_CHANNEL)] = None,
        from_session_id: Annotated[str | None, Field(description=_P_FROM_SESSION)] = None,
        target: Annotated[dict[str, Any] | None, Field(description=_P_TARGET_MSG)] = None,
        artifacts: Annotated[list[str] | None, Field(description=_P_ARTIFACTS)] = None,
        parent_message_id: Annotated[str | None, Field(description=_P_PARENT)] = None,
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
        project_root: Annotated[str, Field(description=_P_ROOT)],
        message_id: Annotated[str, Field(description=_P_MESSAGE_ID)],
        agent_id: Annotated[str | None, Field(description=_P_VIEWER_OPT)] = None,
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
        project_root: Annotated[str, Field(description=_P_ROOT)],
        channel_id: Annotated[str | None, Field(description=_P_CHANNEL)] = None,
        cursor: Annotated[int | None, Field(description=_P_CURSOR)] = None,
        limit: Annotated[int | None, Field(description=_P_LIMIT)] = None,
        agent_id: Annotated[str | None, Field(description=_P_VIEWER_OPT)] = None,
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
        project_root: Annotated[str, Field(description=_P_ROOT)],
        agent_id: Annotated[str, Field(description=_P_WAIT_AGENT)],
        channel_id: Annotated[str | None, Field(description=_P_CHANNEL)] = None,
        cursor: Annotated[int | None, Field(description=_P_CURSOR)] = None,
        limit: Annotated[int | None, Field(description=_P_LIMIT)] = None,
        timeout_seconds: Annotated[int | None, Field(description=_P_TIMEOUT)] = None,
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
    def channel_list(
        project_root: Annotated[str, Field(description=_P_ROOT)],
    ) -> dict[str, Any]:
        """Return the per-workspace seeded channels."""
        return service.list_channels(project_root=project_root)
