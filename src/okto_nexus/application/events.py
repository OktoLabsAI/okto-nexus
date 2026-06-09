"""Event Log slice application service.

Implements the two use cases this slice owns EXCLUSIVELY:

* ``event_get``  - non-blocking, cursor-paginated read of the append-only log
  scoped to a single resolved ``workspace_id``. Events are scanned strictly
  ascending by ``event_id`` (``event_id > cursor``); ``filters`` (equality,
  AND-combined) and visibility (``can_agent_see_event``, imported from
  Routing/Visibility) are applied BEFORE the envelope is built; ``next_cursor``
  advances past every filtered/non-visible event so they are never re-scanned.
* ``event_wait`` - long-poll = ``event_get`` + a poll/sleep loop (no socket,
  thread or subscription). It returns the first non-empty page immediately, or,
  on timeout, ``events=[]`` with the ENTRY cursor unchanged and
  ``timed_out=True``. The wait never blocks longer than
  ``clamp(timeout_seconds, max_wait_timeout_seconds)`` and polls in increments
  of ``poll_interval_ms``.

This module lives in the application layer: it depends only on the ports
(:mod:`okto_nexus.application.ports`), the pure domain helpers
(:mod:`okto_nexus.domain.events`, :mod:`okto_nexus.domain.routing`,
:mod:`okto_nexus.domain.ids`), the error catalogue and :class:`NexusConfig`.
It NEVER imports ``sqlite3`` nor ``mcp`` (enforced by the boundary test). The
``Sleeper``/monotonic clock used by ``event_wait`` are injected so tests stay
deterministic and fast.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from ..config import NexusConfig
from ..domain.events import (
    clamp_limit,
    event_matches_filters,
    event_to_dict,
    normalize_cursor,
    normalize_filters,
    validate_stream,
)
from ..domain.ids import resolve_workspace_id
from ..domain.models import Event
from ..domain.routing import RoutingAgent, can_agent_see_event
from ..errors import ErrorCode, OktoNexusError
from .ports import AgentRepo, Clock, ConnectionFactory, EventRepo, UnitOfWork

#: Default page size when ``limit`` is omitted (also clamped to ``max_limit``).
DEFAULT_EVENT_LIMIT = 100

#: Default ceiling for a single page when no explicit ceiling is injected.
MAX_EVENT_LIMIT = 1000


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True, slots=True)
class _Page:
    """Internal result of a single non-blocking scan."""

    events: list[Event]
    next_cursor: int
    has_more: bool


class EventService:
    """Use-case orchestration for ``event_get`` / ``event_wait``."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        events: EventRepo,
        clock: Clock,
        config: NexusConfig,
        agents: Optional[AgentRepo] = None,
        default_limit: int = DEFAULT_EVENT_LIMIT,
        max_limit: int = MAX_EVENT_LIMIT,
        sleeper: Optional[Callable[[float], None]] = None,
        monotonic: Optional[Callable[[], float]] = None,
    ) -> None:
        self._cf = connection_factory
        self._events = events
        self._agents = agents
        self._clock = clock
        self._config = config
        self._default_limit = max(1, int(default_limit))
        self._max_limit = max(1, int(max_limit))
        self._sleep = sleeper if sleeper is not None else time.sleep
        self._monotonic = monotonic if monotonic is not None else time.monotonic

    # ------------------------------------------------------------------ #
    # Public use cases
    # ------------------------------------------------------------------ #
    def event_get(
        self,
        *,
        project_root: Any,
        agent_id: Any,
        stream: Any,
        cursor: Any = None,
        limit: Any = None,
        filters: Any = None,
    ) -> dict[str, Any]:
        """Non-blocking, cursor-paginated read of the workspace event log.

        Returns ``{events, next_cursor, has_more, timed_out: false}`` where
        ``next_cursor`` is the largest ``event_id`` scanned and ``has_more`` is
        ``True`` iff a matching, visible event exists beyond the returned page.
        """
        workspace_id, agent_id, stream, cursor, limit, filters = self._prepare(
            project_root, agent_id, stream, cursor, limit, filters
        )
        self._touch_agent(agent_id)
        page = self._read_page(workspace_id, agent_id, stream, cursor, limit, filters)
        return self._page_payload(page, timed_out=False)

    def event_wait(
        self,
        *,
        project_root: Any,
        agent_id: Any,
        stream: Any,
        cursor: Any = None,
        limit: Any = None,
        filters: Any = None,
        timeout_seconds: Any = None,
    ) -> dict[str, Any]:
        """Long-poll: ``event_get`` repeated until a non-empty page or timeout.

        Returns the first non-empty page immediately (``timed_out=False``). On
        timeout returns ``events=[]`` with the ENTRY ``cursor`` unchanged and
        ``timed_out=True``. The effective wait never exceeds
        ``clamp(timeout_seconds, max_wait_timeout_seconds)`` plus at most one
        poll interval; ``timeout_seconds <= 0`` performs a single
        ``event_get`` with no sleeping.
        """
        workspace_id, agent_id, stream, cursor, limit, filters = self._prepare(
            project_root, agent_id, stream, cursor, limit, filters
        )
        timeout = self._resolve_timeout(timeout_seconds)
        self._touch_agent(agent_id)
        poll_seconds = max(0.0, self._config.poll_interval_ms / 1000.0)

        # First scan happens before any sleep (0 sleeps when events already
        # exist -> immediate return with timed_out=False).
        page = self._read_page(workspace_id, agent_id, stream, cursor, limit, filters)
        if page.events:
            return self._page_payload(page, timed_out=False)
        if timeout <= 0:
            return self._timed_out_payload(cursor)

        deadline = self._monotonic() + timeout
        while self._monotonic() < deadline:
            self._sleep(poll_seconds)
            page = self._read_page(
                workspace_id, agent_id, stream, cursor, limit, filters
            )
            if page.events:
                return self._page_payload(page, timed_out=False)
        return self._timed_out_payload(cursor)

    # ------------------------------------------------------------------ #
    # Input preparation / validation
    # ------------------------------------------------------------------ #
    def _prepare(
        self,
        project_root: Any,
        agent_id: Any,
        stream: Any,
        cursor: Any,
        limit: Any,
        filters: Any,
    ) -> tuple[str, str, str, int, int, dict[str, str]]:
        """Validate inputs and resolve ``workspace_id`` (no DB access).

        Order is deliberate: ``WORKSPACE_REQUIRED`` (missing ``project_root``)
        precedes ``INVALID_STREAM``, which precedes the remaining
        ``VALIDATION_ERROR`` checks; ``WORKSPACE_UNRESOLVED`` (broken realpath)
        is raised last, only once the request shape is otherwise valid. No scan
        of the log is performed for any of these failures.
        """
        if not _is_nonempty_str(project_root):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_REQUIRED,
                "project_root is required; the server never falls back to a "
                "default/shared workspace.",
                {},
            )
        stream = validate_stream(stream)
        if not _is_nonempty_str(agent_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "agent_id is required (used to enforce event visibility).",
                {"agent_id": agent_id},
            )
        cursor = normalize_cursor(cursor)
        limit = clamp_limit(limit, default=self._default_limit, maximum=self._max_limit)
        filters = normalize_filters(filters)
        # Server-side workspace resolution: sha256(realpath(project_root)).
        # Raises WORKSPACE_UNRESOLVED when realpath cannot be resolved.
        workspace_id = resolve_workspace_id(project_root)
        return workspace_id, agent_id, stream, cursor, limit, filters

    def _resolve_timeout(self, timeout_seconds: Any) -> int:
        """Clamp ``timeout_seconds`` to ``max_wait_timeout_seconds`` (seconds).

        ``None`` defaults to the configured ceiling; ``<= 0`` means a single
        ``event_get`` (no sleeping); a non-integer raises ``VALIDATION_ERROR``.
        """
        ceiling = int(self._config.max_wait_timeout_seconds)
        if timeout_seconds is None:
            return ceiling
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "timeout_seconds must be an integer (seconds).",
                {"timeout_seconds": timeout_seconds},
            )
        if timeout_seconds <= 0:
            return 0
        return min(timeout_seconds, ceiling)

    def _touch_agent(self, agent_id: str) -> None:
        """Best-effort stamp of the caller's ``last_seen_at`` (own uow).

        Presence tracking is a side effect of consuming the log, so it must NEVER
        fail the read: it runs in its own unit of work, no-ops for an agent_id
        that is not a registered identity (``touch`` returns ``False``), and
        swallows a transient write failure (e.g. ``SQLITE_BUSY`` -> ``DB_ERROR``)
        rather than aborting an otherwise-successful read.
        """
        if self._agents is None:
            return
        try:
            with self._cf.unit_of_work() as uow:
                self._agents.touch(uow, agent_id=agent_id, at=self._clock.now_iso())
        except OktoNexusError:
            pass  # best-effort presence; never break a read

    # ------------------------------------------------------------------ #
    # Scanning (a single non-blocking page)
    # ------------------------------------------------------------------ #
    def _read_page(
        self,
        workspace_id: str,
        agent_id: str,
        stream: str,
        cursor: int,
        limit: int,
        filters: Mapping[str, str],
    ) -> _Page:
        """Scan ``event_id > cursor`` (ascending) applying filters + visibility.

        All filtering happens in the application layer so ``next_cursor``
        advances past EVERY discarded event (filtered or non-visible): events
        already scanned are never re-returned. ``has_more`` is ``True`` iff a
        matching+visible event exists strictly beyond the returned page.
        """
        results: list[Event] = []
        next_cursor = cursor
        scan_cursor = cursor
        has_more = False
        batch_size = limit + 1

        with self._cf.unit_of_work() as uow:
            routing_agent = self._build_routing_agent(uow, agent_id, workspace_id)
            while True:
                batch = self._events.list_after(
                    uow,
                    workspace_id=workspace_id,
                    stream=stream,
                    cursor=scan_cursor,
                    limit=batch_size,
                    filters=None,
                )
                if not batch:
                    break
                stop = False
                for event in batch:
                    scan_cursor = event.event_id
                    if not event_matches_filters(event, filters):
                        next_cursor = event.event_id
                        continue
                    if not self._is_visible(routing_agent, event):
                        next_cursor = event.event_id
                        continue
                    if len(results) < limit:
                        results.append(event)
                        next_cursor = event.event_id
                    else:
                        # One more matching+visible event beyond the page.
                        has_more = True
                        stop = True
                        break
                if stop:
                    break
                if len(batch) < batch_size:
                    break  # log exhausted for this stream/workspace
        return _Page(events=results, next_cursor=next_cursor, has_more=has_more)

    def _build_routing_agent(
        self, uow: UnitOfWork, agent_id: str, workspace_id: str
    ) -> RoutingAgent:
        """Construct the routing view of the caller for visibility decisions.

        When an :class:`AgentRepo` is wired, the caller's ``role`` and
        ``capabilities`` are loaded so role/capability-targeted events resolve
        correctly; otherwise a minimal view (id + workspace) is used, which
        still resolves ``public`` and ``direct`` targeting.
        """
        role: str | None = None
        capabilities: Any = None
        if self._agents is not None:
            agent = self._agents.get(uow, agent_id)
            if agent is not None:
                role = agent.role
                capabilities = agent.capabilities
        return RoutingAgent(
            agent_id=agent_id,
            workspace_id=workspace_id,
            role=role,
            capabilities=capabilities,
        )

    @staticmethod
    def _is_visible(routing_agent: RoutingAgent, event: Event) -> bool:
        """Visibility predicate, hardened against malformed event metadata.

        Delegates to ``can_agent_see_event``; a malformed ``visibility``/
        ``target`` (which would raise ``VALIDATION_ERROR``) is treated as
        not-visible so a single poisoned event can never block consumption of a
        stream (an agent is never shown an event that cannot be confirmed
        visible).
        """
        try:
            return bool(can_agent_see_event(routing_agent, event))
        except OktoNexusError:
            return False

    # ------------------------------------------------------------------ #
    # Envelope payload builders
    # ------------------------------------------------------------------ #
    @staticmethod
    def _page_payload(page: _Page, *, timed_out: bool) -> dict[str, Any]:
        return {
            "events": [event_to_dict(event) for event in page.events],
            "next_cursor": page.next_cursor,
            "has_more": page.has_more,
            "timed_out": timed_out,
        }

    @staticmethod
    def _timed_out_payload(cursor: int) -> dict[str, Any]:
        """The canonical timeout result: empty page, ENTRY cursor unchanged."""
        return {
            "events": [],
            "next_cursor": cursor,
            "has_more": False,
            "timed_out": True,
        }
