"""Dashboard read-model (Nexus v2, spec S1 / C6).

``ObservabilityService`` assembles everything the web dashboard renders: the
graph snapshot (agents with DERIVED presence, channels, aggregated message
edges with in-flight lanes, handoffs), paginated histories and the event feed
behind the SSE stream. Strictly read-only by rule br_5865bb88 - the only
write on an authenticated read path is the auth layer's ``last_seen_at``
touch, which happens OUTSIDE this service.

Presence is derived in read-time from session heartbeats, never persisted
(same predicate family as the V1 identity slice), collapsed into the three
exclusive dashboard states:

* ``present``  - an active session heartbeated within ``session_stale_ttl``.
* ``stale``    - an active session, but the heartbeat is older than the
  stale TTL and still inside the ``presence_ttl`` window.
* ``offline``  - no active session, or the heartbeat fell out of the
  presence window entirely.

Pure application code: ports + stdlib only (import boundary enforced).
"""

from __future__ import annotations

from typing import Any

from ..config import NexusConfig
from ..domain.base import iso_to_epoch
from .ports import Clock, ObservabilityQueries, UnitOfWork

#: Default aggregation window for graph edges (hours).
DEFAULT_GRAPH_WINDOW_HOURS = 24

#: Hard ceiling for history pages (defensive LIMIT, FR5).
MAX_PAGE_SIZE = 200

PRESENCE_PRESENT = "present"
PRESENCE_STALE = "stale"
PRESENCE_OFFLINE = "offline"

_LANES = ("unread", "delivered", "read", "parked")


def _epoch_or_none(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return iso_to_epoch(iso)
    except Exception:  # noqa: BLE001 - malformed stamps read as absent
        return None


class ObservabilityService:
    """Read-only aggregates for the dashboard surfaces."""

    def __init__(
        self,
        queries: ObservabilityQueries,
        clock: Clock,
        config: NexusConfig,
    ) -> None:
        self._q = queries
        self._clock = clock
        self._config = config

    # ------------------------------------------------------------------ #
    # Presence derivation
    # ------------------------------------------------------------------ #
    def classify_presence(
        self, *, has_active_session: bool, last_heartbeat_at: str | None
    ) -> str:
        """Collapse session state into present/stale/offline (read-time only)."""
        if not has_active_session:
            return PRESENCE_OFFLINE
        hb_epoch = _epoch_or_none(last_heartbeat_at)
        if hb_epoch is None:
            return PRESENCE_OFFLINE
        age = self._clock.now_epoch() - hb_epoch
        if age < self._config.session_stale_ttl_seconds:
            return PRESENCE_PRESENT
        if age < self._config.presence_ttl_seconds:
            return PRESENCE_STALE
        return PRESENCE_OFFLINE

    # ------------------------------------------------------------------ #
    # Graph snapshot (FR3 / AC5)
    # ------------------------------------------------------------------ #
    def graph_snapshot(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None,
        window_hours: int = DEFAULT_GRAPH_WINDOW_HOURS,
    ) -> dict[str, Any]:
        """The full graph payload for GET /api/v1/graph.

        Nodes are GLOBAL (agents are global identities; presence is global);
        edges, channels and handoffs are scoped to ``workspace_id`` when one
        is given (``None`` = the opt-in "All workspaces" view).
        """
        window_seconds = max(1, int(window_hours)) * 3600
        since_epoch = self._clock.now_epoch() - window_seconds
        since_iso = _epoch_to_iso(since_epoch)

        inbox = self._q.inbox_counts(uow)
        nodes: list[dict[str, Any]] = []
        for row in self._q.agent_rows(uow):
            lanes = inbox.get(row["agent_id"], {})
            nodes.append(
                {
                    "agent_id": row["agent_id"],
                    "role": row.get("role"),
                    "capabilities": row.get("capabilities") or {},
                    "is_active": bool(row.get("is_active", True)),
                    "has_key": bool(row.get("api_key_hash")),
                    "last_seen_at": row.get("last_seen_at"),
                    "presence": self.classify_presence(
                        has_active_session=bool(row.get("active_sessions")),
                        last_heartbeat_at=row.get("last_heartbeat_at"),
                    ),
                    "sessions": int(row.get("active_sessions") or 0),
                    "inbox": {lane: int(lanes.get(lane, 0)) for lane in _LANES},
                }
            )

        return {
            "workspace_id": workspace_id,
            "generated_at": self._clock.now_iso(),
            "window_hours": int(window_hours),
            "nodes": nodes,
            "channels": self._q.channel_rows(uow, workspace_id=workspace_id),
            "edges": {
                "messages": self._q.message_edges(
                    uow, workspace_id=workspace_id, since_iso=since_iso
                ),
                "handoffs": self._q.handoff_rows(
                    uow,
                    workspace_id=workspace_id,
                    statuses=("OPEN", "CLAIMED"),
                ),
            },
        }

    # ------------------------------------------------------------------ #
    # Histories (FR5)
    # ------------------------------------------------------------------ #
    def messages_history(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None = None,
        agent_id: str | None = None,
        channel_id: str | None = None,
        lane: str | None = None,
        since_iso: str | None = None,
        until_iso: str | None = None,
        page: int = 1,
        page_size: int = 50,
        peer_id: str | None = None,
        undelivered_only: bool = False,
        include_body: bool = False,
    ) -> dict[str, Any]:
        if lane is not None and lane not in _LANES:
            raise ValueError(f"invalid lane: {lane!r} (one of {', '.join(_LANES)})")
        if peer_id is not None and agent_id is None:
            raise ValueError("peer requires agent (the conversation is a pair)")
        page = max(1, int(page))
        page_size = min(MAX_PAGE_SIZE, max(1, int(page_size)))
        items, total = self._q.messages_page(
            uow,
            workspace_id=workspace_id,
            agent_id=agent_id,
            channel_id=channel_id,
            lane=lane,
            since_iso=since_iso,
            until_iso=until_iso,
            page=page,
            page_size=page_size,
            peer_id=peer_id,
            undelivered_only=undelivered_only,
            include_body=include_body,
        )
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    def conversation_peers(
        self, uow: UnitOfWork, *, agent_id: str
    ) -> dict[str, Any]:
        """The agent's conversation partners (SQL aggregate; chat peer picker)."""
        if not agent_id:
            raise ValueError("agent is required")
        return self._q.conversation_peers(uow, agent_id=agent_id)

    def handoffs(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        statuses = (status,) if status else None
        return self._q.handoff_rows(uow, workspace_id=workspace_id, statuses=statuses)

    def sessions(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._q.session_rows(uow, workspace_id=workspace_id, status=status)
        for row in rows:
            row["presence"] = self.classify_presence(
                has_active_session=row.get("status") == "active",
                last_heartbeat_at=row.get("last_heartbeat_at"),
            )
        return rows

    def events_page(
        self,
        uow: UnitOfWork,
        *,
        cursor: int = 0,
        workspace_id: str | None = None,
        stream: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = min(self._config.max_event_limit, max(1, int(limit)))
        return self._q.events_after(
            uow,
            cursor=max(0, int(cursor)),
            workspace_id=workspace_id,
            stream=stream,
            limit=limit,
        )


def _epoch_to_iso(epoch: float) -> str:
    from datetime import datetime, timezone

    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")
