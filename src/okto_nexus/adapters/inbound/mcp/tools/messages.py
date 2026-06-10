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

It also registers the S3 clean-break MIGRATION SHIMS ``message_get`` /
``message_list`` / ``message_wait``: clients pinned to the pre-S3 surface get a
prescriptive ``{ok:false, error:{code:"MIGRATED"}}`` envelope naming the exact
replacement tool and parameters, instead of an opaque "Unknown tool" failure.

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
from okto_nexus.envelope import err, require_json_object_param, tool_envelope
from okto_nexus.errors import ErrorCode

#: Error code emitted by the S3 migration shims. ``ErrorCode.MIGRATED`` is the
#: canonical catalogue entry; the literal fallback keeps this module importable
#: against an errors.py that has not landed the new code yet.
_migrated_member = getattr(ErrorCode, "MIGRATED", None)
_MIGRATED_CODE: str = (
    _migrated_member.value if _migrated_member is not None else "MIGRATED"
)

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
_P_FROM_SESSION = (
    "Session_id attributing the message to a specific open session of yours "
    "(optional in trust_mode=open; REQUIRED together with session_secret in "
    "trust_mode=strict)."
)
_P_SESSION_SECRET = (
    "The session_secret returned by session_open for from_session_id (optional "
    "in trust_mode=open - but if supplied it is VALIDATED, a mismatch fails; "
    "REQUIRED together with from_session_id in trust_mode=strict)."
)
#: INVARIANT: byte-identical to the sentence in tools/handoff.py so the SAME
#: concept (a routing target) is documented the SAME way on both tools.
_P_TARGET_TYPE = (
    'Pass target as a raw JSON OBJECT (dict), e.g. {"strategy": "direct", '
    '"agent_id": "<id>"} - NOT as a JSON-encoded string. '
)
#: The routing target selects the recipient set fanned out to inboxes at send
#: time (ADR 0001). Spell out the ``strategy`` enum and each shape.
_P_TARGET_MSG = (
    _P_TARGET_TYPE + "Routing rule selecting who receives this message (optional; omit for a "
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
        presence_ttl_seconds=deps.config.presence_ttl_seconds,
        trust_mode=deps.config.trust_mode,
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
        target: Annotated[Any, Field(description=_P_TARGET_MSG)] = None,
        artifacts: Annotated[list[str] | None, Field(description=_P_ARTIFACTS)] = None,
        parent_message_id: Annotated[str | None, Field(description=_P_PARENT)] = None,
        session_secret: Annotated[
            str | None, Field(description=_P_SESSION_SECRET)
        ] = None,
    ) -> dict[str, Any]:
        """Persist a message and emit ``message.created`` in one transaction.

        A broadcast (no target) reaches the workspace's PRESENT agents only;
        agents excluded for heartbeat staleness are reported explicitly in
        ``excluded_stale`` + ``warning``. In trust_mode=strict pass
        from_session_id + session_secret (from session_open).

        ``target`` is annotated ``Any`` on purpose: the wrapper + application
        layer validate it so a wrong type returns the canonical
        ``VALIDATION_ERROR`` envelope, not an SDK validation error.
        """
        require_json_object_param("target", target)
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
            session_secret=session_secret,
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

    # ------------------------------------------------------------------ #
    # S3 clean-break migration shims. Clients pinned to the pre-S3 surface
    # still call message_get/message_list/message_wait; instead of an opaque
    # "Unknown tool" they get a prescriptive MIGRATED envelope naming the
    # exact replacement call. Each shim declares NO parameters: FastMCP
    # ignores unknown arguments, so EVERY legacy call shape lands here
    # instead of failing schema validation.
    # ------------------------------------------------------------------ #

    def _migrated(message: str, replacements: list[str]) -> dict[str, Any]:
        return err(
            _MIGRATED_CODE,
            message,
            {"replacements": replacements, "removed_in": "S3"},
        )

    @server.tool()
    @tool_envelope
    def message_get() -> dict[str, Any]:
        """MIGRATED (S3): replaced by inbox_pull / inbox_peek / inbox_history. Always returns ok:false code=MIGRATED with the replacement call."""
        return _migrated(
            "message_get was replaced in S3 by the inbox surface. Read messages "
            "addressed to you with inbox_pull(agent_id=<you>) (unread -> "
            "in-flight, returns bodies; acknowledge with inbox_ack), "
            "inbox_peek(agent_id=<you>) for a non-destructive look, or "
            "inbox_history(agent_id=<you>, cursor=..., limit=...) for "
            "already-read messages. To fetch bus traffic by event instead, use "
            "event_get(project_root=..., agent_id=<you>, stream=\"workspace\", "
            'filters={"type": "message.created"}).',
            ["inbox_pull", "inbox_peek", "inbox_history", "event_get"],
        )

    @server.tool()
    @tool_envelope
    def message_list() -> dict[str, Any]:
        """MIGRATED (S3): replaced by inbox_peek / inbox_history (your messages) and event_get (bus traffic). Always returns ok:false code=MIGRATED."""
        return _migrated(
            "message_list was replaced in S3. For YOUR messages use "
            "inbox_peek(agent_id=<you>) (pending: unread + in-flight) or "
            "inbox_history(agent_id=<you>, cursor=..., limit=...) (read "
            "archive, newest-first, paginated). To enumerate the workspace's "
            "message traffic use event_get(project_root=..., agent_id=<you>, "
            'stream="workspace", filters={"type": "message.created"}, '
            "cursor=..., limit=...).",
            ["inbox_peek", "inbox_history", "event_get"],
        )

    @server.tool()
    @tool_envelope
    def message_wait() -> dict[str, Any]:
        """MIGRATED (S3): replaced by inbox_count polling (cheap) or event_wait (explicit blocking). Always returns ok:false code=MIGRATED."""
        return _migrated(
            "message_wait was replaced in S3. Cheapest: call "
            "inbox_count(agent_id=<you>) between turns and inbox_pull when "
            "unread > 0 (then inbox_ack what you processed). To explicitly "
            "block for new traffic use event_wait(project_root=..., "
            'agent_id=<you>, stream="workspace", filters={"type": '
            '"message.created"}, timeout_seconds=<n>) - timeout_seconds '
            "omitted/0 is a non-blocking snapshot; >0 blocks your turn.",
            ["inbox_count", "inbox_pull", "event_wait"],
        )
