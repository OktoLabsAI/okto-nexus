"""MCP inbound tools for the message inbox slice (ADR 0001).

Registers the per-recipient inbox tools, each returning the canonical envelope
via :func:`tool_envelope` so no exception ever crosses the adapter boundary:

* ``inbox_pull``     - the index-free "give me my messages": claim unread (and
  your own lease-expired redeliveries) into in-flight (leased) and return them
  materialised with their body.
* ``inbox_ack``      - move pulled messages to history (read).
* ``inbox_extend``   - renew the lease of in-flight messages mid-turn.
* ``inbox_peek``     - READ-ONLY, envelope-only view of pending (unread +
  in-flight): ``body_preview``/``body_bytes`` instead of the full body.
* ``inbox_count``    - READ-ONLY lane sizes ``{unread, in_flight, read}``.
* ``inbox_history``  - the read lane, newest-first, keyset-paginated.
* ``message_status`` - READ-ONLY sender-side view of a message's deliveries.

The inbox is GLOBAL (keyed by ``agent_id``), so a direct message reaches the
recipient regardless of which workspace it was sent in. This module wires the
concrete SQLite delivery/message/agent repos into ``deps.repos`` (reusing any
already present) and constructs the :class:`InboxService`. It does NOT import the
MCP SDK; the live server is passed into :func:`register`.
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
)
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.identity import SessionTrustGuard
from okto_nexus.adapters.inbound.mcp.projection import (
    apply_to_response,
    parse_profile,
)
from okto_nexus.application.inbox import (
    DEFAULT_INBOX_LEASE_TTL_SECONDS,
    MAX_LEASE_SECONDS,
    MIN_LEASE_SECONDS,
    PEEK_BODY_PREVIEW_CHARS,
    InboxService,
)
from okto_nexus.envelope import tool_envelope

#: Reused parameter descriptions (house style mirrors okto-pulse).
_P_AGENT = "Your agent_id - the GLOBAL inbox to read (a direct message reaches you in any workspace). REQUIRED."
_P_LIMIT = "Max messages to return (optional; default 50, max 200; must be a positive integer)."
_P_MESSAGE_IDS = "The message_id(s) to acknowledge - a single id or a list. REQUIRED. Idempotent (already-read/foreign ids are no-ops)."
_P_CURSOR = "Opaque pagination cursor: pass back the previous page next_cursor (optional; omit = from the newest read messages)."
_P_LEASE_SECONDS = (
    "Lease (seconds) before pulled messages are redelivered (optional; default "
    f"{DEFAULT_INBOX_LEASE_TTL_SECONDS}, clamped {MIN_LEASE_SECONDS}..{MAX_LEASE_SECONDS}); "
    "renew mid-turn with inbox_extend."
)
_P_EXTEND_IDS = "The message_id(s) whose lease to renew - id or list. REQUIRED. All must be in-flight; otherwise the call fails per-message and nothing is extended."
_P_EXTEND_SECONDS = (
    "New lease duration in seconds, counted from now (REQUIRED; clamped to "
    f"{MIN_LEASE_SECONDS}..{MAX_LEASE_SECONDS})."
)
_P_INCLUDE_PARKED = "Also show parked (dead-letter) messages that exhausted redelivery (optional; default false)."
_P_INCLUDE_BODIES = (
    "Return the FULL body instead of the envelope-only body_preview (first "
    f"{PEEK_BODY_PREVIEW_CHARS} chars) + body_bytes (optional; default false; "
    "inbox_pull is the way to consume a message)."
)
_P_STATUS_MESSAGE_ID = "The message_id from message_create whose per-recipient delivery states you want to track. REQUIRED."
_P_PROFILE = "Response size profile - one of: default, summary, full (optional; summary trims per-call tokens)."
#: INVARIANT: the sensitive inbox verbs (pull/ack/extend) share the trust
#: wording with message_create/handoff_* - one credential story bus-wide.
_P_SESSION_TRUST = (
    "Your session_id from session_open (optional in trust_mode=open; REQUIRED "
    "together with session_secret in trust_mode=strict)."
)
_P_SESSION_SECRET = "session_secret from session_open for session_id (optional in open mode but VALIDATED if supplied; REQUIRED in strict mode)."


def build_service(deps: Any) -> InboxService:
    """Wire the SQLite repos into ``deps.repos`` and build the inbox service.

    Idempotent: repos already present are reused so this slice and its peers
    share a single concrete instance per port and one backing store. The
    in-flight lease TTL comes from ``deps.config.inbox_lease_ttl_seconds``
    (env ``OKTO_NEXUS_INBOX_LEASE_TTL_SECONDS`` / ``--inbox-lease-ttl-seconds``,
    parsed FAIL-CLOSED by ``load_config`` - an invalid value aborts startup
    with CONFIG_ERROR instead of silently falling back).
    """
    repos = deps.repos
    if getattr(repos, "deliveries", None) is None:
        repos.deliveries = SqliteMessageDeliveryRepo(deps.clock)
    if getattr(repos, "messages", None) is None:
        repos.messages = SqliteMessageRepo(deps.clock)
    if getattr(repos, "agents", None) is None:
        repos.agents = SqliteAgentRepo(deps.clock)
    if getattr(deps, "event_emitter", None) is None:
        if getattr(repos, "events", None) is None:
            repos.events = SqliteEventRepo(deps.clock)
        deps.event_emitter = SqliteEventEmitter(repos.events)
    return InboxService(
        connection_factory=deps.connection_factory,
        deliveries=repos.deliveries,
        messages=repos.messages,
        agents=repos.agents,
        clock=deps.clock,
        lease_ttl_seconds=deps.config.inbox_lease_ttl_seconds,
        event_emitter=deps.event_emitter,
        config=deps.config,
    )


def register(server: Any, deps: Any) -> None:
    """Register the inbox tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)
    # M10: pull/ack/extend mutate the recipient's read state, so they are
    # credential-gated according to NexusConfig.trust_mode (the read-only
    # peek/count/history/message_status stay open).
    if getattr(deps.repos, "sessions", None) is None:
        deps.repos.sessions = SqliteSessionRepo(deps.clock)
    trust = SessionTrustGuard(
        connection_factory=deps.connection_factory,
        sessions=deps.repos.sessions,
        trust_mode=getattr(deps.config, "trust_mode", "open"),
    )

    @server.tool()
    @tool_envelope
    def inbox_pull(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        limit: Annotated[int | None, Field(description=_P_LIMIT)] = None,
        lease_seconds: Annotated[
            int | None, Field(description=_P_LEASE_SECONDS)
        ] = None,
        session_id: Annotated[str | None, Field(description=_P_SESSION_TRUST)] = None,
        session_secret: Annotated[
            str | None, Field(description=_P_SESSION_SECRET)
        ] = None,
        profile: Annotated[str | None, Field(description=_P_PROFILE)] = None,
    ) -> dict[str, Any]:
        """Take your unread messages into in-flight and return them WITH body (index-free; no cursor). At-least-once: unacked pulls are redelivered. Docs: okto-nexus://reference/tool-docs/inbox."""
        prof = parse_profile(profile)
        trust.require(
            tool="inbox_pull",
            agent_id=agent_id,
            session_id=session_id,
            session_secret=session_secret,
        )
        return apply_to_response(
            service.pull(agent_id=agent_id, limit=limit, lease_seconds=lease_seconds),
            "messages",
            prof,
            kind="inbox",
        )

    @server.tool()
    @tool_envelope
    def inbox_ack(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        message_ids: Annotated[Any, Field(description=_P_MESSAGE_IDS)],
        session_id: Annotated[str | None, Field(description=_P_SESSION_TRUST)] = None,
        session_secret: Annotated[
            str | None, Field(description=_P_SESSION_SECRET)
        ] = None,
    ) -> dict[str, Any]:
        """Acknowledge messages into history (read). Returns {acknowledged, read_message_ids}. Emits a message.read receipt to each sender."""
        trust.require(
            tool="inbox_ack",
            agent_id=agent_id,
            session_id=session_id,
            session_secret=session_secret,
        )
        return service.ack(agent_id=agent_id, message_ids=message_ids)

    @server.tool()
    @tool_envelope
    def inbox_extend(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        message_ids: Annotated[Any, Field(description=_P_EXTEND_IDS)],
        extend_seconds: Annotated[int, Field(description=_P_EXTEND_SECONDS)],
        session_id: Annotated[str | None, Field(description=_P_SESSION_TRUST)] = None,
        session_secret: Annotated[
            str | None, Field(description=_P_SESSION_SECRET)
        ] = None,
    ) -> dict[str, Any]:
        """Renew the lease on in-flight messages you pulled but have not finished (now + extend_seconds). All-or-nothing: if any id is not in-flight the call fails per-message and nothing is extended."""
        trust.require(
            tool="inbox_extend",
            agent_id=agent_id,
            session_id=session_id,
            session_secret=session_secret,
        )
        return service.extend(
            agent_id=agent_id, message_ids=message_ids, extend_seconds=extend_seconds
        )

    @server.tool()
    @tool_envelope
    def inbox_peek(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        limit: Annotated[int | None, Field(description=_P_LIMIT)] = None,
        include_parked: Annotated[
            bool, Field(description=_P_INCLUDE_PARKED)
        ] = False,
        include_bodies: Annotated[
            bool, Field(description=_P_INCLUDE_BODIES)
        ] = False,
        profile: Annotated[str | None, Field(description=_P_PROFILE)] = None,
    ) -> dict[str, Any]:
        """Triage pending messages (unread + in-flight) WITHOUT consuming. READ-ONLY, envelope-only by default (body_preview + body_bytes). include_parked/include_bodies opt in."""
        prof = parse_profile(profile)
        return apply_to_response(
            service.peek(
                agent_id=agent_id,
                limit=limit,
                include_parked=include_parked,
                include_bodies=include_bodies,
            ),
            "messages",
            prof,
            kind="inbox",
        )

    @server.tool()
    @tool_envelope
    def inbox_count(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
    ) -> dict[str, Any]:
        """Return your inbox lane sizes {unread, in_flight, read}. Cheap READ-ONLY between-turns check (pull when unread > 0). Expired in-flight leases count as unread; parked excluded."""
        return service.count(agent_id=agent_id)

    @server.tool()
    @tool_envelope
    def inbox_history(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        cursor: Annotated[str | None, Field(description=_P_CURSOR)] = None,
        limit: Annotated[int | None, Field(description=_P_LIMIT)] = None,
        profile: Annotated[str | None, Field(description=_P_PROFILE)] = None,
    ) -> dict[str, Any]:
        """List your acknowledged (read) messages, newest-first, keyset-paginated (stable pages even while you keep acknowledging). READ-ONLY."""
        prof = parse_profile(profile)
        return apply_to_response(
            service.history(agent_id=agent_id, cursor=cursor, limit=limit),
            "messages",
            prof,
            kind="inbox",
        )

    @server.tool()
    @tool_envelope
    def message_status(
        message_id: Annotated[str, Field(description=_P_STATUS_MESSAGE_ID)],
    ) -> dict[str, Any]:
        """Track a message you SENT: per-recipient delivery states {recipient, status, attempts, read_at} (unread/delivered/read/parked). READ-ONLY."""
        return service.message_status(message_id=message_id)
