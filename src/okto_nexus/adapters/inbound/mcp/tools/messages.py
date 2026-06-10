"""MCP inbound tools for the Channels & Messages slice.

Registers the tools this slice owns exclusively, each returning the canonical
envelope via :func:`tool_envelope` so no exception ever crosses the adapter
boundary:

* ``message_create`` - persist a message, resolve recipients, fan out one inbox
  delivery per recipient, and emit ``message.created`` - all atomically.
* ``channel_create`` - create a channel by name (idempotent).
* ``channel_list``   - the workspace channels (``general`` seeded by default).

Reading messages is the INBOX slice's job (``inbox_pull`` / ``inbox_peek`` /
``inbox_count`` / ``inbox_history`` in ``tools/inbox.py``), per ADR 0001.

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
    SqliteSessionRepo,
    SqliteWorkspaceRepo,
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteChannelRepo,
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.messages import MessageService
from okto_nexus.envelope import tool_envelope

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
    "Channel_id to post into (optional; omit to post with NO channel - channel_id "
    "is left null). Channels are organizational labels only - they do NOT decide "
    "who receives the message (the target does). Enumerate with channel_list; "
    "create with channel_create."
)
_P_CHANNEL_NAME = (
    "Channel name to create - a short topic label, e.g. general, planning, "
    "incident-42. REQUIRED. Idempotent by name: creating an existing name returns "
    "that channel (created=false). Trimmed; max 64 chars; unique per workspace."
)
_P_FROM_SESSION = "Session_id attributing the message to a specific open session of yours (optional)."
#: The routing target selects the recipient set fanned out to inboxes at send
#: time (ADR 0001). Spell out the ``strategy`` enum and each shape.
_P_TARGET_MSG = (
    "Routing rule selecting who receives this message (optional; omit for a "
    "broadcast to the workspace's present agents). Each recipient gets the message "
    "in their inbox; to reach one agent 1:1 use direct. strategy is one of: "
    "direct, capability, role, broadcast, mixed. Shapes: "
    'direct {"strategy":"direct","agent_id":"<id>"} (reaches that GLOBAL agent in '
    "any workspace; unknown agent -> NOT_FOUND); "
    'capability {"strategy":"capability","capability":"<cap>"} (string or list = '
    "any-of; global registry); "
    'role {"strategy":"role","role":"<role>"} (exact, case-sensitive; global); '
    'broadcast {"strategy":"broadcast"} (this workspace\'s active-session agents); '
    'mixed {"strategy":"mixed","rules":[<sub-target>, ...]} (OR of sub-targets). '
    "direct_with_fallback and a broadcast nested in mixed are rejected "
    "(VALIDATION_ERROR) - use a handoff for timed escalation. A group target "
    "matching nobody returns recipients:[] + a warning."
)
_P_ARTIFACTS = (
    "List of artifact_id strings to attach (optional; reference large content "
    "instead of inlining it in body)."
)
_P_PARENT = "Message_id this is a reply to, to thread the conversation (optional)."


def build_service(deps: Any) -> MessageService:
    """Wire the SQLite repos/emitter into ``deps`` and build the service.

    Idempotent: any repo / emitter already present is reused so this slice and
    its peers share a single concrete instance and a single event append path.
    The agents/sessions/deliveries repos back recipient resolution and the inbox
    fan-out performed by ``message_create`` (ADR 0001).
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
    if getattr(repos, "sessions", None) is None:
        repos.sessions = SqliteSessionRepo(deps.clock)
    if getattr(repos, "deliveries", None) is None:
        repos.deliveries = SqliteMessageDeliveryRepo(deps.clock)
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
        sessions=repos.sessions,
        deliveries=repos.deliveries,
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
    def channel_create(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        name: Annotated[str, Field(description=_P_CHANNEL_NAME)],
    ) -> dict[str, Any]:
        """Create a channel by name (idempotent). Channels are organizational labels, not ACLs.

        Returns the channel plus ``created`` (false if the name already existed).
        Any agent in the workspace may read/post to any channel; the channel does
        NOT control who receives a message - the message target does.
        """
        return service.create_channel(project_root=project_root, name=name)

    @server.tool()
    @tool_envelope
    def channel_list(
        project_root: Annotated[str, Field(description=_P_ROOT)],
    ) -> dict[str, Any]:
        """Return the workspace channels (``general`` is seeded by default)."""
        return service.list_channels(project_root=project_root)
