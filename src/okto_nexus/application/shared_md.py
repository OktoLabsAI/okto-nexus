"""shared.md rendering slice - application service.

Owns the single MCP tool ``shared_md_render(workspace_id, limit_events=50)``:
it reads ONLY committed coordination state (via the repository ports) and asks
the injected renderer port to atomically overwrite the per-workspace, human
readable view at ``{home}/workspaces/{workspace_id}/shared.md``.

shared.md is a DERIVED VIEW. SQLite (WAL) remains the single source of truth;
nothing in the system ever reads shared.md back as input - this module never
reads the file either, it only produces it.

Layering: this is part of the application layer, so it depends only on the
ports in :mod:`okto_nexus.application.ports`, the pure domain dataclasses, and
the error catalogue. It NEVER imports ``sqlite3`` nor ``mcp`` (enforced by the
import-boundary test). Filesystem I/O lives entirely behind the
:class:`SharedMdRenderer` port (implemented by an outbound adapter).

Render is a four-section, deterministic FULL OVERWRITE, in this fixed order:

1. relevant agents / active sessions,
2. open tasks,
3. open handoffs,
4. recent events (newest-first by descending ``event_id``, capped).

Determinism is intentional: the rendered file is reproducible solely from the
committed DB state and ``limit_events`` (it embeds no wall-clock timestamp), so
two consecutive renders over identical state are byte-identical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

from ..domain.models import Agent, Event, Handoff, Session, Task
from ..errors import ErrorCode, OktoNexusError
from .ports import (
    AgentRepo,
    Clock,
    ConnectionFactory,
    EventRepo,
    HandoffRepo,
    SessionRepo,
    TaskRepo,
    UnitOfWork,
    WorkspaceRepo,
)

#: Number of fixed sections every render emits (used for ``sections_rendered``).
SECTION_COUNT = 4

#: Default and ceiling for ``limit_events`` when the caller omits / over-asks.
DEFAULT_LIMIT_EVENTS = 50
DEFAULT_MAX_LIMIT_EVENTS = 1000

#: Relevance predicate constants (see FR fr_488c1ca4).
ACTIVE_SESSION_STATUS = "active"
CLOSED_TASK_STATUSES = frozenset({"done", "cancelled"})
OPEN_HANDOFF_STATUSES = frozenset({"open", "claimed"})

#: ``workspace_id`` is lowercase hex of sha256 -> exactly 64 hex chars.
_WORKSPACE_ID_RE = re.compile(r"^[0-9a-f]{64}$")

#: Page size used when draining the (oldest-first) event log to find the
#: newest ``limit_events`` events across all streams.
_EVENT_PAGE_SIZE = 500
#: Defensive cap on paging iterations (avoids an unbounded loop if a misbehaving
#: ``EventRepo`` never advances its cursor).
_EVENT_PAGE_MAX_ITERS = 100_000


# --------------------------------------------------------------------------- #
# Renderer port (owned by this slice; implemented by an outbound adapter)
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class SharedMdView:
    """Immutable snapshot of the rows selected for one workspace's render.

    The application service builds this from committed state (already filtered
    by the relevance predicate and ordered deterministically); the renderer port
    turns it into the markdown file. ``events`` are newest-first.
    """

    workspace_id: str
    limit_events: int
    agents: list[Agent] = field(default_factory=list)
    sessions: list[Session] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    handoffs: list[Handoff] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)


@dataclass(slots=True)
class RenderResult:
    """Outcome of a successful atomic render."""

    path: str
    bytes_written: int
    sections_rendered: int


@runtime_checkable
class SharedMdRenderer(Protocol):
    """Outbound port: format a :class:`SharedMdView` and persist it atomically.

    Implementations MUST write to a temp file in the same directory and
    ``os.replace`` it into ``shared.md`` so no observer ever sees a partial
    file, and MUST raise ``OktoNexusError(RENDER_ERROR)`` on any filesystem /
    serialization failure WITHOUT leaving a partial file behind.
    """

    def render(self, *, view: SharedMdView) -> RenderResult:
        """Render and atomically write the view; return the write result."""
        ...


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _iso_to_epoch(iso: str) -> float:
    """Parse a UTC ISO-8601 timestamp (``...Z`` or ``+00:00``) to a POSIX epoch."""
    text = iso.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


class SharedMdService:
    """Use-case orchestration for ``shared_md_render``.

    Reads coordination state strictly through the injected repository ports and
    delegates the atomic write to the :class:`SharedMdRenderer` port. Repos for
    sibling slices (tasks/handoffs/events/agents/sessions) are optional: when a
    port is not wired the corresponding section simply renders empty, so this
    slice stays shippable before every sibling has landed.
    """

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        workspaces: WorkspaceRepo,
        renderer: SharedMdRenderer,
        clock: Clock,
        agents: Optional[AgentRepo] = None,
        sessions: Optional[SessionRepo] = None,
        tasks: Optional[TaskRepo] = None,
        handoffs: Optional[HandoffRepo] = None,
        events: Optional[EventRepo] = None,
        max_limit_events: int = DEFAULT_MAX_LIMIT_EVENTS,
    ) -> None:
        self._cf = connection_factory
        self._workspaces = workspaces
        self._renderer = renderer
        self._clock = clock
        self._agents = agents
        self._sessions = sessions
        self._tasks = tasks
        self._handoffs = handoffs
        self._events = events
        self._max_limit = int(max_limit_events)

    # ------------------------------------------------------------------ #
    # Public use case
    # ------------------------------------------------------------------ #
    def shared_md_render(
        self, *, workspace_id: Any, limit_events: Any = None
    ) -> dict[str, Any]:
        """Render the four-section shared.md for ``workspace_id``.

        Validates input and reads only committed state; writes/modifies NO file
        on any error. Returns the canonical ``data`` payload::

            {path, workspace_id, bytes_written, sections_rendered,
             limit_events, generated_at}

        Raises (mapped to the canonical catalog by the tool envelope):

        * ``WORKSPACE_REQUIRED`` - ``workspace_id`` missing / empty.
        * ``VALIDATION_ERROR``   - malformed ``workspace_id`` or invalid
          ``limit_events`` (not a positive int within the configured maximum).
        * ``NOT_FOUND``          - well-formed but unknown ``workspace_id``.
        * ``DB_ERROR``           - a SQLite read fails (propagated from a repo).
        * ``RENDER_ERROR``       - the atomic write fails (from the renderer).
        """
        ws_id = self._validate_workspace_id(workspace_id)
        limit = self._validate_limit_events(limit_events)

        now_iso = self._clock.now_iso()

        # Single read transaction over committed state (no writes).
        with self._cf.unit_of_work() as uow:
            if self._workspaces.get(uow, ws_id) is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    "workspace not found.",
                    {"workspace_id": ws_id},
                )
            view = self._read_view(uow, ws_id, limit, now_iso)

        # Filesystem write happens AFTER the read transaction is closed, so a DB
        # read failure never produces a file and the write never holds the txn.
        result = self._renderer.render(view=view)

        return {
            "path": result.path,
            "workspace_id": ws_id,
            "bytes_written": result.bytes_written,
            "sections_rendered": result.sections_rendered,
            "limit_events": limit,
            "generated_at": now_iso,
        }

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def _validate_workspace_id(self, workspace_id: Any) -> str:
        if not _is_nonempty_str(workspace_id):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_REQUIRED,
                "workspace_id is required.",
                {},
            )
        if not _WORKSPACE_ID_RE.match(workspace_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "workspace_id must be a 64-character lowercase hex string.",
                {"workspace_id": workspace_id},
            )
        return workspace_id

    def _validate_limit_events(self, limit_events: Any) -> int:
        if limit_events is None:
            return DEFAULT_LIMIT_EVENTS
        # bool is a subclass of int but is never a valid count.
        if isinstance(limit_events, bool) or not isinstance(limit_events, int):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "limit_events must be a positive integer.",
                {"limit_events": limit_events},
            )
        if limit_events <= 0 or limit_events > self._max_limit:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"limit_events must be in 1..{self._max_limit}.",
                {"limit_events": limit_events, "max_limit_events": self._max_limit},
            )
        return limit_events

    # ------------------------------------------------------------------ #
    # Committed-state reads (strictly workspace-scoped, deterministic order)
    # ------------------------------------------------------------------ #
    def _read_view(
        self, uow: UnitOfWork, ws_id: str, limit: int, now_iso: str
    ) -> SharedMdView:
        sessions = self._read_sessions(uow, ws_id)
        agents = self._read_agents(uow, sessions)
        active_sessions = sorted(
            (s for s in sessions if s.status == ACTIVE_SESSION_STATUS),
            key=lambda s: s.session_id,
        )
        tasks = self._read_open_tasks(uow, ws_id)
        handoffs = self._read_open_handoffs(uow, ws_id, now_iso)
        events = self._read_recent_events(uow, ws_id, limit)
        return SharedMdView(
            workspace_id=ws_id,
            limit_events=limit,
            agents=agents,
            sessions=active_sessions,
            tasks=tasks,
            handoffs=handoffs,
            events=events,
        )

    def _read_sessions(self, uow: UnitOfWork, ws_id: str) -> list[Session]:
        if self._sessions is None:
            return []
        return [s for s in self._sessions.list(uow, workspace_id=ws_id)]

    def _read_agents(self, uow: UnitOfWork, sessions: list[Session]) -> list[Agent]:
        # Agents are global identities with no list-by-workspace port; an agent
        # is "relevant" to the workspace iff it owns a session there. Derive the
        # set from the workspace's sessions and fetch each by id (deterministic
        # order by agent_id).
        if self._agents is None:
            return []
        agent_ids = sorted({s.agent_id for s in sessions})
        agents: list[Agent] = []
        for agent_id in agent_ids:
            agent = self._agents.get(uow, agent_id)
            if agent is not None:
                agents.append(agent)
        return agents

    def _read_open_tasks(self, uow: UnitOfWork, ws_id: str) -> list[Task]:
        if self._tasks is None:
            return []
        rows = self._tasks.list(uow, workspace_id=ws_id)
        open_tasks = [t for t in rows if t.status not in CLOSED_TASK_STATUSES]
        open_tasks.sort(key=lambda t: (t.created_at, t.task_id))
        return open_tasks

    def _read_open_handoffs(
        self, uow: UnitOfWork, ws_id: str, now_iso: str
    ) -> list[Handoff]:
        if self._handoffs is None:
            return []
        rows = self._handoffs.list(uow, workspace_id=ws_id)
        now_epoch = self._safe_epoch(now_iso)
        open_handoffs = [
            h
            for h in rows
            if h.status in OPEN_HANDOFF_STATUSES
            and not self._is_expired(h, now_epoch)
        ]
        open_handoffs.sort(key=lambda h: (h.created_at, h.handoff_id))
        return open_handoffs

    def _read_recent_events(
        self, uow: UnitOfWork, ws_id: str, limit: int
    ) -> list[Event]:
        if self._events is None:
            return []
        # ``list_after`` is oldest-first and cursor-based; drain the whole
        # workspace stream (``stream=None`` selects all streams) then keep the
        # newest ``limit`` by descending event_id.
        collected: list[Event] = []
        cursor = 0
        for _ in range(_EVENT_PAGE_MAX_ITERS):
            batch = self._events.list_after(
                uow,
                workspace_id=ws_id,
                stream=None,
                cursor=cursor,
                limit=_EVENT_PAGE_SIZE,
                filters=None,
            )
            if not batch:
                break
            collected.extend(batch)
            last_id = batch[-1].event_id
            if last_id is None or last_id <= cursor:
                break  # cursor not advancing -> stop defensively
            cursor = last_id
            if len(batch) < _EVENT_PAGE_SIZE:
                break
        collected.sort(
            key=lambda e: e.event_id if e.event_id is not None else -1,
            reverse=True,
        )
        return collected[:limit]

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _safe_epoch(iso: str) -> Optional[float]:
        try:
            return _iso_to_epoch(iso)
        except (ValueError, TypeError):
            return None

    def _is_expired(self, handoff: Handoff, now_epoch: Optional[float]) -> bool:
        if handoff.lease_expires_at is None or now_epoch is None:
            return False
        lease = self._safe_epoch(handoff.lease_expires_at)
        if lease is None:
            return False
        return lease <= now_epoch
