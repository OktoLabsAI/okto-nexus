"""MCP inbound tools for the message inbox slice (ADR 0001).

Registers the per-recipient inbox tools, each returning the canonical envelope
via :func:`tool_envelope` so no exception ever crosses the adapter boundary:

* ``inbox_pull``     - the index-free "give me my messages": claim unread (and
  your own lease-expired redeliveries) into in-flight (leased) and return them
  materialised with their body.
* ``inbox_ack``      - move pulled messages to history (read).
* ``inbox_extend``   - renew the lease of in-flight messages mid-turn.
* ``inbox_peek``     - READ-ONLY view of pending (unread + in-flight).
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

from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.inbox import (
    DEFAULT_INBOX_LEASE_TTL_SECONDS,
    MAX_LEASE_SECONDS,
    MIN_LEASE_SECONDS,
    InboxService,
)
from okto_nexus.envelope import tool_envelope

#: Reused parameter descriptions (house style mirrors okto-pulse).
_P_AGENT = (
    "Your agent_id - the GLOBAL inbox to read. A direct message reaches you "
    "regardless of which workspace it was sent in. REQUIRED."
)
_P_LIMIT = "Max messages to return (optional; default 50, max 200; must be a positive integer)."
_P_MESSAGE_IDS = (
    "The message_id(s) to acknowledge into history - a single id string or a list "
    "of them. REQUIRED. Idempotent: already-read or foreign ids are no-ops."
)
_P_CURSOR = (
    "Opaque pagination cursor: pass back the next_cursor from the previous history "
    "page (optional; omit to start from the newest read messages)."
)
_P_LEASE_SECONDS = (
    "How long (seconds) the pulled messages stay leased to you before they are "
    f"redelivered (optional; default {DEFAULT_INBOX_LEASE_TTL_SECONDS}, clamped "
    f"to {MIN_LEASE_SECONDS}..{MAX_LEASE_SECONDS}). Size it to your expected "
    "processing turn, or renew mid-turn with inbox_extend."
)
_P_EXTEND_IDS = (
    "The message_id(s) whose lease to renew - a single id string or a list of "
    "them. REQUIRED. All must be in-flight (pulled by you, unacknowledged, "
    "lease still valid); otherwise the call fails with a per-message reason "
    "and nothing is extended."
)
_P_EXTEND_SECONDS = (
    "New lease duration in seconds, counted from now (REQUIRED; clamped to "
    f"{MIN_LEASE_SECONDS}..{MAX_LEASE_SECONDS})."
)
_P_INCLUDE_PARKED = (
    "Also show parked (dead-letter) messages - deliveries that exhausted their "
    "redelivery attempts and will never be redelivered (optional; default false)."
)
_P_STATUS_MESSAGE_ID = (
    "The message_id returned by message_create - the message whose "
    "per-recipient delivery states you want to track. REQUIRED."
)


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
    return InboxService(
        connection_factory=deps.connection_factory,
        deliveries=repos.deliveries,
        messages=repos.messages,
        agents=repos.agents,
        clock=deps.clock,
        lease_ttl_seconds=deps.config.inbox_lease_ttl_seconds,
    )


def register(server: Any, deps: Any) -> None:
    """Register the inbox tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def inbox_pull(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        limit: Annotated[int | None, Field(description=_P_LIMIT)] = None,
        lease_seconds: Annotated[
            int | None, Field(description=_P_LEASE_SECONDS)
        ] = None,
    ) -> dict[str, Any]:
        """Take your unread messages into in-flight and return them with their body.

        Index-free: the server tracks your per-recipient read state, so you never
        pass a cursor. At-least-once: pulled messages are leased; if you do not
        ``inbox_ack`` them before the lease elapses they are redelivered on a
        later pull. Long turn? Size the lease with ``lease_seconds`` or renew it
        with ``inbox_extend``. A message redelivered too many times is parked
        (dead-letter) - see ``inbox_peek`` with ``include_parked``.
        """
        return service.pull(agent_id=agent_id, limit=limit, lease_seconds=lease_seconds)

    @server.tool()
    @tool_envelope
    def inbox_ack(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        message_ids: Annotated[Any, Field(description=_P_MESSAGE_IDS)],
    ) -> dict[str, Any]:
        """Acknowledge messages into history (read), freeing your inbox queue.

        Returns ``{acknowledged: <count>}``. Ack only what you have finished
        handling; unacked in-flight messages are redelivered after their lease.
        """
        return service.ack(agent_id=agent_id, message_ids=message_ids)

    @server.tool()
    @tool_envelope
    def inbox_extend(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        message_ids: Annotated[Any, Field(description=_P_EXTEND_IDS)],
        extend_seconds: Annotated[int, Field(description=_P_EXTEND_SECONDS)],
    ) -> dict[str, Any]:
        """Renew the lease on messages you pulled but have not finished handling.

        Sets the lease of YOUR in-flight deliveries to now + ``extend_seconds``
        so a long turn does not trigger duplicate redelivery. All-or-nothing:
        if any id is not in-flight (never pulled / lease already expired /
        already acknowledged / parked) the call fails with a per-message
        reason and nothing is extended.
        """
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
    ) -> dict[str, Any]:
        """Look at your pending messages (unread + in-flight) WITHOUT consuming them.

        READ-ONLY: nothing is leased, moved, or swept (an in-flight message
        whose lease elapsed is shown as ``unread``). Use ``inbox_pull`` to
        actually take them; pass ``include_parked=true`` to also inspect
        dead-lettered messages.
        """
        return service.peek(
            agent_id=agent_id, limit=limit, include_parked=include_parked
        )

    @server.tool()
    @tool_envelope
    def inbox_count(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
    ) -> dict[str, Any]:
        """Return your inbox lane sizes ``{unread, in_flight, read}``.

        A cheap, READ-ONLY between-turns check to decide whether to
        ``inbox_pull`` (``unread > 0``). Expired in-flight leases are counted
        as ``unread``. Parked (dead-letter) messages are excluded - inspect
        them with ``inbox_peek`` and ``include_parked=true``.
        """
        return service.count(agent_id=agent_id)

    @server.tool()
    @tool_envelope
    def inbox_history(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        cursor: Annotated[str | None, Field(description=_P_CURSOR)] = None,
        limit: Annotated[int | None, Field(description=_P_LIMIT)] = None,
    ) -> dict[str, Any]:
        """List your acknowledged (read) messages, newest-first, with pagination.

        READ-ONLY and keyset-paginated: pages stay stable (no duplicates) even
        while you keep acknowledging new messages between pages.
        """
        return service.history(agent_id=agent_id, cursor=cursor, limit=limit)

    @server.tool()
    @tool_envelope
    def message_status(
        message_id: Annotated[str, Field(description=_P_STATUS_MESSAGE_ID)],
    ) -> dict[str, Any]:
        """Track a message you SENT: the per-recipient delivery states.

        READ-ONLY. Returns ``{message_id, deliveries, count}`` where each
        delivery is ``{recipient, status, attempts, read_at}`` and status is
        one of: ``unread`` (queued, or its lease expired and it awaits
        redelivery), ``delivered`` (recipient pulled it - in flight), ``read``
        (acknowledged), ``parked`` (dead-lettered after exhausting redelivery
        attempts). Use it instead of re-sending when a recipient seems silent.
        """
        return service.message_status(message_id=message_id)
