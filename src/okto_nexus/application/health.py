"""Coordination-health read-model (spec 7df9b1e0, I7).

``HealthService`` is the SINGLE use case behind both the ``coordination_health``
MCP tool and ``GET /api/v1/workspaces/{id}/health``: it fetches every input in
ONE read-only unit of work, buckets presence by REUSING the
``ObservabilityService`` classifier (the present/stale/offline rule keeps its
single source of truth - the ``WorkspaceListService`` precedent), and delegates
the ENTIRE payload assembly to the pure
:func:`okto_nexus.domain.health.compute_health` - tool/REST parity by
construction.

Strictly read-only AND passive: zero writes, no events, no trace, and no
heartbeat / ``last_seen_at`` touch - the tool takes no agent identity at all
(dec_ed36e779): a health probe must never turn its own observer into a
"present" agent inside the very presence metric it reports.

Gating (RD1): the agent-facing MCP tool is gated LIVE by ``feature_health``
via :meth:`HealthService.require_feature_health` (flag OFF ->
VALIDATION_ERROR ``{feature_health: false}``; the tool stays registered in
both states). The operator's REST read is NOT gated (the I6 precedent); the
route validates the window itself (400 ``INVALID_WINDOW``, analytics parity)
before calling in.

Application layer: ports + pure domain + the error catalogue only - never
``sqlite3`` nor ``mcp`` (import-boundary test).
"""

from __future__ import annotations

from typing import Any

from ..config import NexusConfig
from ..domain.base import iso_to_epoch
from ..domain.handoff import STATUS_OPEN
from ..domain.health import (
    DEFAULT_WINDOW,
    HEALTH_WINDOWS,
    AgentUnread,
    HandoffLifecycleEvent,
    HealthInputs,
    PresenceCounts,
    UnclaimedHandoff,
    compute_health,
    is_valid_window,
)
from ..domain.ids import resolve_workspace_id
from ..errors import ErrorCode, OktoNexusError
from .observability import ObservabilityService
from .ports import Clock, ConnectionFactory, ObservabilityQueries, WorkspaceRepo
from .workspace_analytics import _epoch_to_iso


def _epoch_or_none(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return iso_to_epoch(iso)
    except Exception:  # noqa: BLE001 - malformed stamps read as absent
        return None


class HealthService:
    """Assemble the windowed coordination-health report for one workspace."""

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

    # ------------------------------------------------------------------ #
    # Gating (tool path ONLY - the REST route never calls this)
    # ------------------------------------------------------------------ #
    def require_feature_health(self) -> None:
        """Fail-closed LIVE gate on the agent-facing tool (RD1).

        Read from the shared ``NexusConfig`` per call, so a dashboard toggle
        takes effect without a restart. The tool stays REGISTERED in both
        states; OFF simply rejects the call. The operator's REST read is a
        separate, ungated surface (I6 precedent).
        """
        if not bool(getattr(self._config, "feature_health", False)):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "Coordination health is disabled on this server "
                "(feature_health=false). An operator can enable the "
                "'feature_health' setting on the dashboard.",
                {"feature_health": False},
            )

    # ------------------------------------------------------------------ #
    # Input resolution
    # ------------------------------------------------------------------ #
    def _resolve_window(self, window: Any) -> str:
        """Default absent/blank to :data:`DEFAULT_WINDOW`; fail-closed else.

        The enum has a SINGLE source (``domain.health.HEALTH_WINDOWS``); an
        unsupported value raises ``VALIDATION_ERROR`` naming the allowed set
        (RD4). The REST route pre-validates via :func:`is_valid_window` and
        maps to 400 ``INVALID_WINDOW`` before reaching here.
        """
        if window is None or (isinstance(window, str) and not window.strip()):
            return DEFAULT_WINDOW
        if not is_valid_window(window):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"window must be one of {', '.join(HEALTH_WINDOWS)}.",
                {"window": window, "allowed": list(HEALTH_WINDOWS)},
            )
        return str(window)

    def _resolve_workspace_id(self, project_root: Any, workspace_id: Any) -> str:
        """One of ``workspace_id`` (REST) or ``project_root`` (tool).

        ``workspace_id`` wins when both arrive (the REST route addresses the
        workspace directly); the tool always passes ``project_root``, hashed
        server-side (``WORKSPACE_UNRESOLVED`` when irresolvable). Neither ->
        ``WORKSPACE_REQUIRED``.
        """
        if isinstance(workspace_id, str) and workspace_id.strip():
            return workspace_id.strip()
        if isinstance(project_root, str) and project_root.strip():
            return resolve_workspace_id(project_root)
        raise OktoNexusError(
            ErrorCode.WORKSPACE_REQUIRED,
            "project_root (or workspace_id) is required to resolve the workspace.",
            {},
        )

    # ------------------------------------------------------------------ #
    # The read
    # ------------------------------------------------------------------ #
    def health(
        self,
        *,
        project_root: Any = None,
        workspace_id: Any = None,
        window: Any = None,
    ) -> dict[str, Any]:
        """The full health payload (the ``data`` of the canonical envelope).

        Validates the window (fail-closed), resolves the workspace, verifies
        it EXISTS (``NOT_FOUND`` - health is a passive read, it never upserts
        a workspace into being), then runs every query inside ONE
        ``write=False`` unit of work and hands the parsed inputs to the pure
        :func:`compute_health`.
        """
        window = self._resolve_window(window)
        wid = self._resolve_workspace_id(project_root, workspace_id)
        now_epoch = self._clock.now_epoch()
        since_iso = _epoch_to_iso(now_epoch - HEALTH_WINDOWS[window])

        with self._cf.unit_of_work(write=False) as uow:
            if self._workspaces.get(uow, wid) is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"Workspace '{wid}' does not exist.",
                    {"workspace_id": wid},
                )

            message_count = self._q.workspace_message_count(
                uow, workspace_id=wid, since_iso=since_iso
            )
            event_count = self._q.workspace_event_stats(
                uow, workspace_id=wid, since_iso=since_iso
            )["count"]

            unclaimed = [
                UnclaimedHandoff(handoff_id=row["handoff_id"], created_at_epoch=epoch)
                for row in self._q.handoff_rows(
                    uow, workspace_id=wid, statuses=(STATUS_OPEN,)
                )
                if not row.get("claimed_by")
                and (epoch := _epoch_or_none(row.get("created_at"))) is not None
            ]

            raw_events, truncated = self._q.handoff_lifecycle_events(
                uow, workspace_id=wid, since_iso=since_iso
            )
            lifecycle = [
                HandoffLifecycleEvent(
                    handoff_id=handoff_id,
                    event_type=event_type,
                    created_at_epoch=epoch,
                )
                for handoff_id, event_type, created_at in raw_events
                if (epoch := _epoch_or_none(created_at)) is not None
            ]

            unread = [
                AgentUnread(agent_id=row["agent_id"], unread=int(row["unread"]))
                for row in self._q.workspace_unread_by_agent(uow, workspace_id=wid)
            ]

            presence = self._presence_counts(uow, workspace_id=wid)

        inputs = HealthInputs(
            workspace_id=wid,
            window=window,
            message_count=message_count,
            event_count=event_count,
            lifecycle_events=lifecycle,
            lifecycle_truncated=truncated,
            unclaimed=unclaimed,
            unread=unread,
            presence=presence,
        )
        return compute_health(inputs, now_epoch=now_epoch)

    def _presence_counts(self, uow: Any, *, workspace_id: str) -> PresenceCounts:
        """Bucket the workspace's agents present/stale/offline.

        The exact ``WorkspaceListService`` aggregation: presence is per
        DISTINCT AGENT (never per session row) - each agent keeps its
        freshest ACTIVE-session heartbeat, the agent's own ``last_seen_at``
        (bumped by every active coordination verb) folds in, and
        ``classify_presence`` runs ONCE per agent, so the present/stale/
        offline rule stays single-sourced in the ``ObservabilityService``.
        """
        last_seen_by_agent = {
            r["agent_id"]: r.get("last_seen_at") for r in self._q.agent_rows(uow)
        }
        agent_ids: set[str] = set()
        has_active: dict[str, bool] = {}
        best_hb: dict[str, str] = {}
        for sess in self._q.session_rows(uow, workspace_id=workspace_id):
            aid = sess.get("agent_id")
            if aid is None:
                continue
            agent_ids.add(aid)
            if sess.get("status") == "active":
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
        return PresenceCounts(
            present=buckets["present"],
            stale=buckets["stale"],
            offline=buckets["offline"],
        )
