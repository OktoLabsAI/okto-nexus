"""MCP inbound tools for the message inbox slice (ADR 0001).

Registers the per-recipient inbox tools, each returning the canonical envelope
via :func:`tool_envelope` so no exception ever crosses the adapter boundary:

* ``inbox_pull``    - the index-free "give me my messages": take unread into
  in-flight (leased) and return them materialised with their body.
* ``inbox_ack``     - move pulled messages to history (read).
* ``inbox_peek``    - non-destructive view of pending (unread + in-flight).
* ``inbox_count``   - lane sizes ``{unread, in_flight, read}``.
* ``inbox_history`` - the read lane, newest-first, paginated.

The inbox is GLOBAL (keyed by ``agent_id``), so a direct message reaches the
recipient regardless of which workspace it was sent in. This module wires the
concrete SQLite delivery/message/agent repos into ``deps.repos`` (reusing any
already present) and constructs the :class:`InboxService`. It does NOT import the
MCP SDK; the live server is passed into :func:`register`.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Mapping

from pydantic import Field

from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.adapters.outbound.sqlite.messages_repo import (
    SqliteMessageDeliveryRepo,
    SqliteMessageRepo,
)
from okto_nexus.application.inbox import (
    DEFAULT_INBOX_LEASE_TTL_SECONDS,
    InboxService,
)
from okto_nexus.envelope import tool_envelope

#: Environment knob for the in-flight lease TTL (seconds). Not part of
#: ``NexusConfig``, so it is resolved here in the inbound adapter.
INBOX_LEASE_TTL_ENV = "OKTO_NEXUS_INBOX_LEASE_TTL_SECONDS"

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


def _resolve_lease_ttl(env: Mapping[str, str]) -> int:
    """Resolve the in-flight lease TTL from the environment (positive int)."""
    raw = env.get(INBOX_LEASE_TTL_ENV)
    if raw is None or not str(raw).strip():
        return DEFAULT_INBOX_LEASE_TTL_SECONDS
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_INBOX_LEASE_TTL_SECONDS
    return value if value > 0 else DEFAULT_INBOX_LEASE_TTL_SECONDS


def build_service(deps: Any, env: Mapping[str, str] | None = None) -> InboxService:
    """Wire the SQLite repos into ``deps.repos`` and build the inbox service.

    Idempotent: repos already present are reused so this slice and its peers
    share a single concrete instance per port and one backing store.
    """
    environ = env if env is not None else os.environ
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
        lease_ttl_seconds=_resolve_lease_ttl(environ),
    )


def register(server: Any, deps: Any) -> None:
    """Register the inbox tools on ``server`` (FastMCP ``@server.tool()``)."""
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def inbox_pull(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        limit: Annotated[int | None, Field(description=_P_LIMIT)] = None,
    ) -> dict[str, Any]:
        """Take your unread messages into in-flight and return them with their body.

        Index-free: the server tracks your per-recipient read state, so you never
        pass a cursor. At-least-once: pulled messages are leased; if you do not
        ``inbox_ack`` them before the lease elapses they are redelivered on a
        later pull. Acknowledge what you have processed with ``inbox_ack``.
        """
        return service.pull(agent_id=agent_id, limit=limit)

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
    def inbox_peek(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        limit: Annotated[int | None, Field(description=_P_LIMIT)] = None,
    ) -> dict[str, Any]:
        """Look at your pending messages (unread + in-flight) WITHOUT consuming them.

        Does not lease or move anything (it does sweep expired leases so the
        statuses are accurate). Use ``inbox_pull`` to actually take them.
        """
        return service.peek(agent_id=agent_id, limit=limit)

    @server.tool()
    @tool_envelope
    def inbox_count(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
    ) -> dict[str, Any]:
        """Return your inbox lane sizes ``{unread, in_flight, read}``.

        A cheap between-turns check to decide whether to ``inbox_pull``
        (``unread > 0``). Expired in-flight leases are counted as ``unread``.
        """
        return service.count(agent_id=agent_id)

    @server.tool()
    @tool_envelope
    def inbox_history(
        agent_id: Annotated[str, Field(description=_P_AGENT)],
        cursor: Annotated[str | None, Field(description=_P_CURSOR)] = None,
        limit: Annotated[int | None, Field(description=_P_LIMIT)] = None,
    ) -> dict[str, Any]:
        """List your acknowledged (read) messages, newest-first, with pagination."""
        return service.history(agent_id=agent_id, cursor=cursor, limit=limit)
