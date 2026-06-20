"""Workspace rich-list read-model (the operator overview behind GET /workspaces).

Turns the dead Workspaces screen into a first-class panel: for EVERY known
workspace (not just the ones with a live session), assemble identity + a 24h
activity rollup + presence counts + a health block - all read-only and scoped
by ``workspace_id``.

Pure application layer: depends only on ports + the presence classifier of the
``ObservabilityService`` (reused so the present/stale/offline rule stays the
single source of truth). No SQL, no HTTP here. ``root_realpath`` disclosure is
gated by the live ``expose_workspace_path`` setting (BR9): off -> the path is
redacted; the per-call ``include_paths`` of the MCP ``workspace_list`` tool is a
separate, agent-facing surface and never drives this gating.
"""

from __future__ import annotations

from typing import Any

from ..config import NexusConfig
from .observability import ObservabilityService
from .ports import Clock, ConnectionFactory, ObservabilityQueries, WorkspaceRepo
from .workspace_analytics import _epoch_to_iso

#: The rollup window for the list view (FR2): the last 24 hours.
ROLLUP_WINDOW_SECONDS = 86_400


class WorkspaceListService:
    """Assemble the rich per-workspace list for the operator dashboard."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        queries: ObservabilityQueries,
        workspaces: WorkspaceRepo,
        observability: ObservabilityService,
        clock: Clock,
        config: NexusConfig,
    ) -> None:
        self._cf = connection_factory
        self._q = queries
        self._workspaces = workspaces
        self._obs = observability
        self._clock = clock
        self._config = config

    def list_workspaces(
        self,
        *,
        default_workspace_id: str | None = None,
        expose_path: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Every known workspace with identity + 24h rollups + health.

        ``expose_path`` defaults to the live ``expose_workspace_path`` setting
        (read here so a dashboard toggle takes effect without a restart). The
        list is ordered by ``last_seen_at`` descending (most recently active
        first); a workspace with no ``last_seen_at`` sorts last.
        """
        if expose_path is None:
            expose_path = bool(getattr(self._config, "expose_workspace_path", False))
        since_iso = _epoch_to_iso(self._clock.now_epoch() - ROLLUP_WINDOW_SECONDS)

        with self._cf.unit_of_work(write=False) as uow:
            workspaces = self._workspaces.list_all(uow)
            # Agent activity (global last_seen_at) folds into presence so an
            # agent that is plainly working reads online even without a live
            # session. Fetched ONCE here, not per workspace.
            last_seen_by_agent = {
                r["agent_id"]: r.get("last_seen_at")
                for r in self._q.agent_rows(uow)
            }
            items = [
                self._build(
                    uow,
                    ws,
                    since_iso=since_iso,
                    default_workspace_id=default_workspace_id,
                    expose_path=expose_path,
                    last_seen_by_agent=last_seen_by_agent,
                )
                for ws in workspaces
            ]
        # last_seen_at desc; None (never-seen) sorts last via the "" floor.
        items.sort(key=lambda it: (it["last_seen_at"] or ""), reverse=True)
        return items

    def _build(
        self,
        uow,
        ws,
        *,
        since_iso: str,
        default_workspace_id: str | None,
        expose_path: bool,
        last_seen_by_agent: dict[str, str | None],
    ) -> dict[str, Any]:
        wid = ws.workspace_id

        message_count = self._q.workspace_message_count(
            uow, workspace_id=wid, since_iso=since_iso
        )
        event_stats = self._q.workspace_event_stats(
            uow, workspace_id=wid, since_iso=since_iso
        )
        handoffs = self._q.handoff_rows(
            uow, workspace_id=wid, statuses=("OPEN", "CLAIMED")
        )
        open_handoff_count = len(handoffs)
        open_handoffs_unclaimed = sum(
            1 for h in handoffs if h["status"] == "OPEN" and not h.get("claimed_by")
        )

        # Presence is per DISTINCT AGENT, not per session. A workspace
        # accumulates many (mostly closed) session rows over its life, so
        # counting sessions makes "Agents in workspace" explode (e.g. 0/0/83 for
        # 3 agents). For each agent we keep its freshest ACTIVE-session heartbeat
        # and fold in the agent's own last_seen_at (activity), then classify
        # ONCE - so an agent that is plainly working reads present even with no
        # live session (e.g. pulling its durable inbox without session_open).
        # stale_sessions (a HEALTH signal) stays session-based - it is literally
        # a count of stale sessions.
        agent_ids: set[str] = set()
        has_active: dict[str, bool] = {}
        best_hb: dict[str, str] = {}
        stale_sessions = 0
        for sess in self._q.session_rows(uow, workspace_id=wid):
            active = sess.get("status") == "active"
            if (
                self._obs.classify_presence(
                    has_active_session=active,
                    last_heartbeat_at=sess.get("last_heartbeat_at"),
                )
                == "stale"
            ):
                stale_sessions += 1
            aid = sess.get("agent_id")
            if aid is None:
                continue
            agent_ids.add(aid)
            if active:
                has_active[aid] = True
                hb = sess.get("last_heartbeat_at")
                # Canonical fixed-width ISO -> lexicographic max is chronological.
                if hb and (aid not in best_hb or hb > best_hb[aid]):
                    best_hb[aid] = hb
            else:
                has_active.setdefault(aid, False)

        buckets = {"present": 0, "stale": 0, "offline": 0}
        for aid in agent_ids:
            buckets[
                self._obs.classify_presence(
                    has_active_session=has_active.get(aid, False),
                    last_heartbeat_at=best_hb.get(aid),
                    last_seen_at=last_seen_by_agent.get(aid),
                )
            ] += 1
        present, stale, offline = (
            buckets["present"],
            buckets["stale"],
            buckets["offline"],
        )

        delivery = self._q.workspace_delivery_health(uow, workspace_id=wid)

        has_path = ws.root_realpath is not None
        exposed = expose_path and has_path
        return {
            "workspace_id": wid,
            "display_name": ws.display_name,
            "root_realpath": ws.root_realpath if exposed else None,
            "path_redacted": has_path and not expose_path,
            "created_at": ws.created_at,
            "last_seen_at": ws.last_seen_at,
            "is_default": wid == default_workspace_id,
            "message_count": message_count,
            "event_count": event_stats["count"],
            "last_event_at": event_stats["last_event_at"],
            "open_handoff_count": open_handoff_count,
            "presence": {"present": present, "stale": stale, "offline": offline},
            "health": {
                "open_handoffs_unclaimed": open_handoffs_unclaimed,
                "stale_sessions": stale_sessions,
                "parked_messages_deadletter": delivery["parked"],
                "inbox_backlog_unread": delivery["unread"],
            },
        }
