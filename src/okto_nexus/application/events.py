"""Event Log slice application service.

Implements the two use cases this slice owns EXCLUSIVELY:

* ``event_get``  - non-blocking, cursor-paginated read of the append-only log
  scoped to a single resolved ``workspace_id``. Events are scanned strictly
  ascending by ``event_id`` (``event_id > cursor``); ``filters`` (equality,
  AND-combined) and visibility (``can_agent_see_event``, imported from
  Routing/Visibility) are applied BEFORE the envelope is built; ``next_cursor``
  advances past every filtered/non-visible event so they are never re-scanned.
* ``event_wait`` - long-poll = ``event_get`` + a bounded wait on the injected
  :class:`Waiter` port (no socket, thread or subscription HERE - the blocking
  strategy is the adapter's). It returns the first non-empty page immediately,
  or, on timeout, ``events=[]`` with the ENTRY cursor unchanged and
  ``timed_out=True``. The wait never blocks longer than
  ``clamp(timeout_seconds, max_wait_timeout_seconds)``, and the log is
  RE-SCANNED only when the waiter reports a store change (V1: a sleep-poll
  gated by ``PRAGMA data_version``; a future SSE/notify waiter swaps in with
  no change to this module).

plus ``latest_cursor`` - the O(1) position-only complement (MAX ``event_id``,
no scan) that resolves "the end of the log" for followers starting at
``latest``.

This module lives in the application layer: it depends only on the ports
(:mod:`okto_nexus.application.ports`), the pure domain helpers
(:mod:`okto_nexus.domain.events`, :mod:`okto_nexus.domain.routing`,
:mod:`okto_nexus.domain.ids`), the error catalogue and :class:`NexusConfig`.
It NEVER imports ``sqlite3`` nor ``mcp`` (enforced by the boundary test), and
it holds NO blocking primitive (no ``time.sleep`` anywhere in this layer): all
waiting goes through the :class:`Waiter` port, so tests stay deterministic and
fast and a push transport never needs to touch this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from ..config import DEFAULT_MAX_EVENT_LIMIT, NexusConfig
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
from ..domain.tag_selector import reachable
from ..errors import ErrorCode, OktoNexusError
from .permissions import permission_set_for
from .ports import AgentRepo, Clock, ConnectionFactory, EventRepo, Waiter

#: Default page size when ``limit`` is omitted (also clamped to ``max_limit``).
DEFAULT_EVENT_LIMIT = 100

#: Default ceiling for a single page when no explicit ceiling is injected.
#: The live ceiling is a ``NexusConfig`` knob (``max_event_limit``, env
#: ``OKTO_NEXUS_MAX_EVENT_LIMIT``, parsed fail-closed at startup); its default
#: is aliased here under the historic name.
MAX_EVENT_LIMIT = DEFAULT_MAX_EVENT_LIMIT


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True, slots=True)
class _Page:
    """Internal result of a single non-blocking scan."""

    events: list[Event]
    next_cursor: int
    has_more: bool


class _LegacySleeperWaiter:
    """Adapts legacy injected ``sleeper``/``monotonic`` callables to ``Waiter``.

    Pre-waiter semantics, preserved exactly: every poll interval the wait
    "wakes" and REPORTS A CHANGE, so the caller re-scans each interval (no
    ``data_version`` gating - the callables carry no store knowledge). Kept for
    callers that inject their own sleep, e.g. the tail follower's test
    harness; production wiring uses ``ConnectionFactory.change_waiter()``.

    Pure: both callables are injected, so this layer still never imports a
    blocking primitive. When ``monotonic`` is omitted, a virtual clock
    advanced by the requested sleep amounts keeps deadline math consistent.
    """

    def __init__(
        self,
        sleeper: Optional[Callable[[float], None]],
        monotonic: Optional[Callable[[], float]],
        poll_interval_s: float,
    ) -> None:
        self._sleeper = sleeper
        self._monotonic_fn = monotonic
        self._poll_interval_s = max(poll_interval_s, 0.0)
        self._virtual_t = 0.0

    def monotonic(self) -> float:
        if self._monotonic_fn is not None:
            return self._monotonic_fn()
        return self._virtual_t

    def snapshot(self) -> Any:
        return None  # no store knowledge: every wake is a presumed change

    def wait_for_change(self, since: Any, timeout_s: float) -> bool:
        delay = min(self._poll_interval_s, max(0.0, float(timeout_s)))
        if delay > 0 and self._sleeper is not None:
            self._sleeper(delay)
        self._virtual_t += delay
        return True  # presume changed -> caller re-scans (pre-waiter cadence)


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
        waiter: Optional[Waiter] = None,
        sleeper: Optional[Callable[[float], None]] = None,
        monotonic: Optional[Callable[[], float]] = None,
        touch_on_read: bool = True,
    ) -> None:
        self._cf = connection_factory
        self._events = events
        self._agents = agents
        self._clock = clock
        self._config = config
        self._default_limit = max(1, int(default_limit))
        self._max_limit = max(1, int(max_limit))
        # Presence semantics knob: True (the MCP path) keeps stamping the
        # caller's ``last_seen_at`` on every read; False builds a PASSIVE
        # observer (the detached ``okto-nexus tail`` follower) whose reads are
        # not activity - so ``last_seen_at`` keeps meaning "most recent action
        # on the bus" instead of being held eternally fresh by a monitor.
        self._touch_on_read = bool(touch_on_read)
        # Blocking seam resolution: explicit waiter > legacy sleeper shim >
        # the store's own change waiter (data_version-gated sleep-poll).
        # ``sleeper``/``monotonic`` are the legacy injection seam (kept for the
        # tail follower's deterministic tests); a lone ``monotonic`` without a
        # ``sleeper`` cannot block and is ignored.
        if waiter is not None:
            self._waiter: Waiter = waiter
        elif sleeper is not None:
            self._waiter = _LegacySleeperWaiter(
                sleeper, monotonic, max(0.0, config.poll_interval_ms / 1000.0)
            )
        else:
            self._waiter = connection_factory.change_waiter()

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
        return self._event_get_prepared(
            workspace_id, agent_id, stream, cursor, limit, filters
        )

    def event_get_for_workspace(
        self,
        *,
        workspace_id: Any,
        agent_id: Any,
        stream: Any,
        cursor: Any = None,
        limit: Any = None,
        filters: Any = None,
    ) -> dict[str, Any]:
        """``event_get`` variant for already-authenticated workspace scopes.

        Used by the EPT data plane: the token row supplies ``workspace_id`` and
        the client cannot override it with a ``project_root``.
        """
        workspace_id, agent_id, stream, cursor, limit, filters = (
            self._prepare_workspace_id(
                workspace_id, agent_id, stream, cursor, limit, filters
            )
        )
        return self._event_get_prepared(
            workspace_id, agent_id, stream, cursor, limit, filters
        )

    def _event_get_prepared(
        self,
        workspace_id: str,
        agent_id: str,
        stream: str,
        cursor: int,
        limit: int,
        filters: dict[str, str],
    ) -> dict[str, Any]:
        self._require_read_permission(agent_id)
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
        """Long-poll: ``event_get`` re-scanned on store changes until timeout.

        Returns the first non-empty page immediately (``timed_out=False``). On
        timeout returns ``events=[]`` with the ENTRY ``cursor`` unchanged and
        ``timed_out=True``. The effective wait never exceeds
        ``clamp(timeout_seconds, max_wait_timeout_seconds)`` plus at most one
        poll interval; ``timeout_seconds <= 0`` performs a single
        ``event_get`` with no waiting. Blocking is delegated to the
        :class:`Waiter` port; the log is re-scanned ONLY when the waiter
        reports a change (a commit by any process), never once per interval.
        """
        workspace_id, agent_id, stream, cursor, limit, filters = self._prepare(
            project_root, agent_id, stream, cursor, limit, filters
        )
        return self._event_wait_prepared(
            workspace_id,
            agent_id,
            stream,
            cursor,
            limit,
            filters,
            timeout_seconds,
        )

    def event_wait_for_workspace(
        self,
        *,
        workspace_id: Any,
        agent_id: Any,
        stream: Any,
        cursor: Any = None,
        limit: Any = None,
        filters: Any = None,
        timeout_seconds: Any = None,
    ) -> dict[str, Any]:
        """``event_wait`` variant for EPT/server-derived workspace scopes."""
        workspace_id, agent_id, stream, cursor, limit, filters = (
            self._prepare_workspace_id(
                workspace_id, agent_id, stream, cursor, limit, filters
            )
        )
        return self._event_wait_prepared(
            workspace_id,
            agent_id,
            stream,
            cursor,
            limit,
            filters,
            timeout_seconds,
        )

    def _event_wait_prepared(
        self,
        workspace_id: str,
        agent_id: str,
        stream: str,
        cursor: int,
        limit: int,
        filters: dict[str, str],
        timeout_seconds: Any,
    ) -> dict[str, Any]:
        self._require_read_permission(agent_id)
        timeout = self._resolve_timeout(timeout_seconds)
        # Touch BEFORE the change-token snapshot: the presence stamp is this
        # caller's own write, and snapshotting after it keeps the first wait
        # from waking spuriously on it.
        self._touch_agent(agent_id)
        waiter = self._waiter

        # Snapshot precedes the first scan (Waiter contract): a write landing
        # between the scan and the wait wakes the first wait_for_change instead
        # of being slept through.
        token = waiter.snapshot() if timeout > 0 else None
        page = self._read_page(workspace_id, agent_id, stream, cursor, limit, filters)
        if page.events:
            return self._page_payload(page, timed_out=False)
        if timeout <= 0:
            return self._timed_out_payload(cursor)

        deadline = waiter.monotonic() + timeout
        while True:
            remaining = deadline - waiter.monotonic()
            if remaining <= 0:
                return self._timed_out_payload(cursor)
            if not waiter.wait_for_change(token, remaining):
                # The full remaining window elapsed with NO commit anywhere:
                # a re-scan provably returns the same empty page, so the
                # timeout is answered without touching the log again.
                return self._timed_out_payload(cursor)
            token = waiter.snapshot()
            page = self._read_page(
                workspace_id, agent_id, stream, cursor, limit, filters
            )
            if page.events:
                return self._page_payload(page, timed_out=False)

    def latest_cursor(
        self,
        *,
        project_root: Any,
        agent_id: Any,
        stream: Any,
    ) -> int:
        """Resolve the stream's CURRENT END as a cursor, in O(1) (no scan).

        Returns the largest ``event_id`` in the (workspace, stream) scope -
        ``0`` for an empty stream - so a follower starting at ``latest`` sees
        only subsequently-appended events. Position-only: it answers WHERE the
        log ends via an indexed ``MAX``, replacing the page-walk that made
        follower startup O(log size). Visibility is irrelevant for a position
        (the walk-based resolution already advanced past non-visible events,
        so both yield the same cursor). Validation order and the best-effort
        presence touch match ``event_get``.
        """
        workspace_id, agent_id, stream, _, _, _ = self._prepare(
            project_root, agent_id, stream, None, None, None
        )
        return self.latest_cursor_for_workspace(
            workspace_id=workspace_id, agent_id=agent_id, stream=stream
        )

    def latest_cursor_for_workspace(
        self,
        *,
        workspace_id: Any,
        agent_id: Any,
        stream: Any,
    ) -> int:
        """Resolve the stream end for an already-authenticated workspace."""
        workspace_id, agent_id, stream, _, _, _ = self._prepare_workspace_id(
            workspace_id, agent_id, stream, None, None, None
        )
        self._require_read_permission(agent_id)
        self._touch_agent(agent_id)
        with self._cf.unit_of_work(write=False) as uow:
            return int(
                self._events.max_event_id(uow, workspace_id=workspace_id, stream=stream)
            )

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
        return self._prepare_workspace_id(
            workspace_id, agent_id, stream, cursor, limit, filters
        )

    def _prepare_workspace_id(
        self,
        workspace_id: Any,
        agent_id: Any,
        stream: Any,
        cursor: Any,
        limit: Any,
        filters: Any,
    ) -> tuple[str, str, str, int, int, dict[str, str]]:
        if not _is_nonempty_str(workspace_id):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_REQUIRED,
                "workspace_id is required.",
                {"workspace_id": workspace_id},
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
        return workspace_id, agent_id, stream, cursor, limit, filters

    def _resolve_timeout(self, timeout_seconds: Any) -> int:
        """Clamp ``timeout_seconds`` to ``max_wait_timeout_seconds`` (seconds).

        ``None`` defaults to the configured ceiling; ``<= 0`` means a single
        ``event_get`` (no sleeping). Accepts an int OR an integer STRING - exactly
        as the shared cursor/limit parsers already tolerate, because MCP harnesses
        and LLM tool-callers routinely serialize numbers as strings; without this
        the canonical ``event_wait`` long-poll monitor is unusable from such a
        harness. ``bool``, a non-integer (e.g. ``2.5``), or a non-numeric value
        raises ``VALIDATION_ERROR``.
        """
        ceiling = int(self._config.max_wait_timeout_seconds)
        if timeout_seconds is None:
            return ceiling
        if isinstance(timeout_seconds, bool) or not isinstance(
            timeout_seconds, (int, str)
        ):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "timeout_seconds must be an integer number of seconds.",
                {"timeout_seconds": timeout_seconds},
            )
        try:
            value = int(timeout_seconds)
        except (TypeError, ValueError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "timeout_seconds must be an integer number of seconds.",
                {"timeout_seconds": timeout_seconds},
            ) from None
        if value <= 0:
            return 0
        return min(value, ceiling)

    def _require_read_permission(self, agent_id: str) -> None:
        """Gate ``events.read`` (migration 011) in its own read-only uow.

        Unlike presence touching, a denial here MUST fail the read: an
        Observer-restricted agent may watch, but an agent whose events.read
        flag is off gets the canonical PERMISSION_DENIED envelope.
        """
        with self._cf.unit_of_work(write=False) as uow:
            permission_set_for(self._agents, uow, agent_id).require("events", "read")

    def _touch_agent(self, agent_id: str) -> None:
        """Best-effort stamp of the caller's ``last_seen_at`` (own uow).

        Presence tracking is a side effect of consuming the log, so it must NEVER
        fail the read: it runs in its own unit of work, no-ops for an agent_id
        that is not a registered identity (``touch`` returns ``False``), and
        swallows a transient write failure (e.g. ``SQLITE_BUSY`` -> ``DB_ERROR``)
        rather than aborting an otherwise-successful read.

        A service built with ``touch_on_read=False`` (the passive tail
        follower) skips the stamp entirely: passive observation is not
        activity, keeping the ``last_seen_at`` liveness signal honest.
        """
        if not self._touch_on_read or self._agents is None:
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

        with self._cf.unit_of_work(write=False) as uow:
            # ONE batched agent lookup per page (F2): the registry is read
            # once and reused for the viewer's own profile and for every
            # actor-reachability check of this scan - never per event.
            registry: dict[str, Any] | None = None
            if self._agents is not None:
                registry = {a.agent_id: a for a in self._agents.list(uow)}
            viewer_profile = registry.get(agent_id) if registry is not None else None
            routing_agent = self._build_routing_agent(
                viewer_profile, agent_id, workspace_id
            )
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
                    if not self._actor_reachable(
                        viewer_profile, agent_id, event, registry
                    ):
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
        self, profile: Any, agent_id: str, workspace_id: str
    ) -> RoutingAgent:
        """Construct the routing view of the caller for visibility decisions.

        ``profile`` is the caller's registry row from the page's single
        batched lookup (or ``None`` when unregistered / no repo is wired);
        its ``role``, ``capabilities`` and ``tags`` are carried over so role-,
        capability- and tag-targeted events resolve correctly. A minimal view
        (id + workspace) still resolves ``public`` and ``direct`` targeting.
        """
        return RoutingAgent(
            agent_id=agent_id,
            workspace_id=workspace_id,
            role=getattr(profile, "role", None),
            capabilities=getattr(profile, "capabilities", None),
            tags=getattr(profile, "tags", None),
        )

    @staticmethod
    def _actor_reachable(
        viewer_profile: Any, viewer_id: str, event: Event, registry: Any
    ) -> bool:
        """Whether the event's ACTOR is reachable from the viewer (F2).

        Composes WITH :func:`can_agent_see_event` - it never replaces it
        (visibility != claimability). Carve-outs: the viewer's OWN events are
        never hidden (ADR 0001) and system events without an actor always
        pass. ``registry`` is the page's single batched agent lookup;
        ``None`` (no agent repo wired) means unrestricted. The operator feed
        (SSE ``/api/v1/stream`` + REST ``/api/v1/events``) never routes
        through here.
        """
        if registry is None:
            return True
        actor = getattr(event, "actor_agent_id", None)
        if actor is None or str(actor) == str(viewer_id):
            return True
        viewer_view = (
            viewer_profile if viewer_profile is not None else {"agent_id": viewer_id}
        )
        actor_profile = registry.get(str(actor)) or {"agent_id": str(actor)}
        return reachable(viewer_view, actor_profile)

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
