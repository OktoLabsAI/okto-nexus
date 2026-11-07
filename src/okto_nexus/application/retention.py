"""Retention slice application service (M7): bounded growth for the store.

Everything in Okto Nexus accumulates by design - events are append-only,
acknowledged deliveries become history, closed sessions stay as audit rows -
all inside ONE shared ``nexus.db``. Without retention the file grows without
bound and every scan slows down. :class:`RetentionService.prune` deletes rows
that aged past their configured window, under hard SAFETY INVARIANTS:

* Only TERMINAL lanes are eligible. ``read`` deliveries and ``closed``
  sessions age out; ``unread``/``delivered``/``parked`` deliveries and
  ``active``/``stale`` sessions are NEVER deleted regardless of age (the lane
  predicates are baked into the adapters' SQL, so the protection is
  structural, not a runtime check).
* MESSAGES are an exception (spec D-EMB-6, by owner directive): they
  expire by PURE AGE (``created_at``), independent of delivery status, with a
  HARD minimum window of 7 days (fail-closed). The reaper deletes a message's
  ``message_deliveries`` and its embedding (the latter via ``ON DELETE
  CASCADE``) alongside it. This deliberately relaxes the historical "Nexus
  never deletes an undelivered message" invariant.
* Coordination request references expire after a fixed 30-day window,
  including pending approvals. They survive resource deletion before expiry.
  Expiring a reference never changes the underlying resource or approval.
* Handoffs, tasks, channels, agents, workspaces and artifacts are
  never touched - in particular a non-terminal handoff (OPEN/CLAIMED) can
  never be pruned because NO handoff delete path exists at all.
* Deletes run in BOUNDED BATCHES, each in its own write transaction, so the
  WAL writer lock is held briefly and concurrent agents keep flowing.
  ``max_batches`` caps the work of a single call (the cheap, incremental
  "opportunistic reaper" mode used by ``auto_prune_on_start``); the report
  says whether each table was drained (``complete``) so an operator knows to
  run ``okto-nexus admin prune`` for a full pass.
* ``dry_run=True`` only COUNTS (read-only snapshot, no writer lock) - nothing
  is deleted and ``VACUUM`` is skipped.

Windows default to the ``NexusConfig`` retention section
(``retention_events_keep_days`` 30d / ``retention_read_deliveries_keep_days``
14d / ``retention_closed_sessions_keep_days`` 7d, env
``OKTO_NEXUS_RETENTION_*``, parsed fail-closed) and can be overridden per
call. This module lives in the application layer: it depends only on the
ports, :class:`NexusConfig`, the error catalogue and the pure domain time
helpers - it NEVER imports ``sqlite3`` nor ``mcp`` (enforced by the boundary
test). The prune-specific repo capabilities are declared as slice-local
Protocols below; the SQLite repos satisfy them structurally.
"""

from __future__ import annotations

from functools import partial
from typing import Any, Protocol, runtime_checkable

from ..config import MIN_RETENTION_MESSAGES_KEEP_DAYS, NexusConfig
from ..domain.base import iso_plus
from ..domain.coordination_requests import RETENTION_DAYS
from ..errors import ErrorCode, OktoNexusError
from .ports import Clock, ConnectionFactory, CoordinationRequestRepo, UnitOfWork

#: Rows deleted per write transaction. Small enough that one batch holds the
#: WAL writer lock only briefly; large enough that a full prune of a busy
#: store finishes in few transactions.
DEFAULT_PRUNE_BATCH_SIZE = 500

#: Batch budget PER TABLE for the opportunistic ``auto_prune_on_start`` reaper:
#: bounded startup work (at most ``budget * batch_size`` rows per table per
#: start), trading completeness for a fast, predictable boot. Backlog drains
#: incrementally across starts, or in one pass via ``okto-nexus admin prune``.
AUTO_PRUNE_MAX_BATCHES = 4
OBSERVATION_PRUNE_BATCH_MAX = 1000

_SECONDS_PER_DAY = 86400.0


# --------------------------------------------------------------------------- #
# Slice-local ports: the prune capabilities this service needs from the repos.
# Declared HERE (not in application.ports) because retention is the only
# consumer; the concrete SQLite repos satisfy them structurally.
# --------------------------------------------------------------------------- #
@runtime_checkable
class PrunableEventRepo(Protocol):
    """Events: count/delete rows older than a cutoff (terminal by nature)."""

    def count_before(self, uow: UnitOfWork, *, cutoff: str,
                     exclude_observations: bool = False) -> int:
        ...

    def prune_before(self, uow: UnitOfWork, *, cutoff: str, limit: int,
                     exclude_observations: bool = False) -> int:
        ...


@runtime_checkable
class PrunableDeliveryRepo(Protocol):
    """Deliveries: count/delete ``read`` (history) rows ONLY."""

    def count_read_before(self, uow: UnitOfWork, *, cutoff: str) -> int:
        ...

    def prune_read_before(
        self, uow: UnitOfWork, *, cutoff: str, limit: int
    ) -> int:
        ...


@runtime_checkable
class PrunableSessionRepo(Protocol):
    """Sessions: count/delete ``closed`` rows ONLY."""

    def count_closed_before(self, uow: UnitOfWork, *, cutoff: str) -> int:
        ...

    def prune_closed_before(
        self, uow: UnitOfWork, *, cutoff: str, limit: int
    ) -> int:
        ...


@runtime_checkable
class PrunableMessageRepo(Protocol):
    """Messages: count/delete rows older than a cutoff by PURE AGE.

    Deletes a message's deliveries (and its embedding via CASCADE) alongside it;
    the predicate is ``created_at < cutoff`` regardless of delivery status.
    """

    def count_before(self, uow: UnitOfWork, *, cutoff: str) -> int:
        ...

    def prune_before(self, uow: UnitOfWork, *, cutoff: str, limit: int) -> int:
        ...


class PrunableObservationRepo(Protocol):
    """Auxiliary cleanup preserves heads, generation fences and their tokens."""

    def count_prunable(self, uow: UnitOfWork, *, now: str) -> dict[str, int]: ...

    def prune(self, uow: UnitOfWork, *, now: str, limit: int) -> dict[str, int]: ...

    def count_prunable_events(self, uow: UnitOfWork, *, cutoff: str,
                              max_events: int) -> int: ...

    def prune_events(self, uow: UnitOfWork, *, cutoff: str, max_events: int,
                     limit: int) -> int: ...


def _validate_keep_days(name: str, value: Any) -> int:
    """Coerce a keep-days override to a non-negative int, fail-closed.

    ``0`` is valid ("keep nothing older than right now"); ``bool`` is rejected
    explicitly (an ``int`` subclass that is almost certainly a caller bug).
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{name} must be an integer number of days (0 keeps nothing "
            "older than now); omit it to use the configured default.",
            {name: value},
        )
    if value < 0:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{name} must be >= 0 days.",
            {name: value},
        )
    return value


def _validate_messages_keep_days(value: Any) -> int:
    """Coerce a messages keep-days override, fail-closed with the HARD min 7.

    Mirrors :func:`_validate_keep_days` but enforces the owner-mandated floor:
    a message-retention window below 7 days is rejected (the same minimum the
    config parser enforces at startup), so neither path can purge the bus more
    aggressively than the policy allows.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "messages_keep_days must be an integer number of days "
            f"(minimum {MIN_RETENTION_MESSAGES_KEEP_DAYS}); omit it to use the "
            "configured default.",
            {"messages_keep_days": value},
        )
    if value < MIN_RETENTION_MESSAGES_KEEP_DAYS:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"messages_keep_days must be >= {MIN_RETENTION_MESSAGES_KEEP_DAYS} "
            "days (fail-closed minimum).",
            {"messages_keep_days": value},
        )
    return value


class RetentionService:
    """Use-case orchestration for retention pruning (and optional VACUUM)."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        clock: Clock,
        config: NexusConfig,
        events: PrunableEventRepo,
        deliveries: PrunableDeliveryRepo,
        sessions: PrunableSessionRepo,
        messages: PrunableMessageRepo,
        coordination_requests: CoordinationRequestRepo | None = None,
        observations: PrunableObservationRepo | None = None,
        batch_size: int = DEFAULT_PRUNE_BATCH_SIZE,
    ) -> None:
        self._cf = connection_factory
        self._clock = clock
        self._config = config
        self._events = events
        self._deliveries = deliveries
        self._sessions = sessions
        self._messages = messages
        self._coordination_requests = coordination_requests
        self._observations = observations
        self._batch_size = max(1, int(batch_size))

    @classmethod
    def from_deps(cls, deps: Any) -> "RetentionService":
        """Build the service from a bootstrap ``Deps`` container.

        The composition-root convenience used by the ``admin prune`` CLI and
        the server's ``auto_prune_on_start`` hook: reuses the already-wired
        concrete repos so retention shares the exact store every other slice
        writes to.
        """
        repos = deps.repos
        return cls(
            connection_factory=deps.connection_factory,
            clock=deps.clock,
            config=deps.config,
            events=repos.events,
            deliveries=repos.deliveries,
            sessions=repos.sessions,
            messages=repos.messages,
            coordination_requests=repos.coordination_requests,
            observations=getattr(repos, "observations", None),
        )

    # ------------------------------------------------------------------ #
    # Public use case
    # ------------------------------------------------------------------ #
    def prune(
        self,
        *,
        events_keep_days: Any = None,
        read_deliveries_keep_days: Any = None,
        closed_sessions_keep_days: Any = None,
        messages_keep_days: Any = None,
        dry_run: bool = False,
        max_batches: Any = None,
        vacuum: bool = False,
    ) -> dict[str, Any]:
        """Delete (or count, with ``dry_run``) rows older than their window.

        Each ``*_keep_days`` overrides the ``NexusConfig`` default when given
        (``None`` -> config). ``max_batches`` caps the number of delete batches
        PER TABLE (``None`` = drain fully); a capped run reports
        ``complete=False`` for tables with backlog left. ``vacuum=True``
        compacts the file after a real (non-dry) prune.

        Returns the report::

            {
              "dry_run": bool,
              "now": iso, "windows_days": {...}, "cutoffs": {...},
              "tables": {
                "events":             {"deleted": int, "complete": bool},
                "message_deliveries": {"deleted": int, "complete": bool},
                "sessions":           {"deleted": int, "complete": bool},
              },
              "total_deleted": int,
              "protected": str,   # the lanes prune can NEVER touch
              "vacuum": {"requested": bool, "ran": bool, "skipped_reason": str|None},
            }

        With ``dry_run=True``, ``deleted`` is the count that WOULD be deleted
        and nothing is written. Raises ``VALIDATION_ERROR`` for malformed
        overrides and ``DB_ERROR`` (retryable on lock contention) from the
        store.
        """
        windows = {
            "events": (
                self._config.retention_events_keep_days
                if events_keep_days is None
                else _validate_keep_days("events_keep_days", events_keep_days)
            ),
            "read_deliveries": (
                self._config.retention_read_deliveries_keep_days
                if read_deliveries_keep_days is None
                else _validate_keep_days(
                    "read_deliveries_keep_days", read_deliveries_keep_days
                )
            ),
            "closed_sessions": (
                self._config.retention_closed_sessions_keep_days
                if closed_sessions_keep_days is None
                else _validate_keep_days(
                    "closed_sessions_keep_days", closed_sessions_keep_days
                )
            ),
            "messages": (
                self._config.retention_messages_keep_days
                if messages_keep_days is None
                else _validate_messages_keep_days(messages_keep_days)
            ),
        }
        budget = self._validate_max_batches(max_batches)

        now = self._clock.now_iso()
        # iso_plus is the canonical-form gate: a non-canonical injected clock
        # fails closed here instead of producing a cutoff that compares wrong
        # lexicographically against stored timestamps.
        cutoffs = {
            key: iso_plus(now, -days * _SECONDS_PER_DAY)
            for key, days in windows.items()
        }
        event_count, event_delete = self._events.count_before, self._events.prune_before
        if self._observations is not None:
            # OBS events live in the same physical log, but have their own age
            # and row cap. Disjoint predicates keep dry-run totals accurate and
            # prevent the generic event window from bypassing OBS policy.
            event_count = partial(event_count, exclude_observations=True)
            event_delete = partial(event_delete, exclude_observations=True)

        tables = {
            "events": self._run_table(
                cutoffs["events"],
                count=event_count,
                delete=event_delete,
                dry_run=dry_run,
                budget=budget,
            ),
            "message_deliveries": self._run_table(
                cutoffs["read_deliveries"],
                count=self._deliveries.count_read_before,
                delete=self._deliveries.prune_read_before,
                dry_run=dry_run,
                budget=budget,
            ),
            "sessions": self._run_table(
                cutoffs["closed_sessions"],
                count=self._sessions.count_closed_before,
                delete=self._sessions.prune_closed_before,
                dry_run=dry_run,
                budget=budget,
            ),
            # Messages expire by PURE AGE (D-EMB-6): the delete cascades to their
            # deliveries (repo) and embeddings (FK CASCADE). Same batched, own-txn
            # loop, so it never holds the WAL writer lock continuously.
            "messages": self._run_table(
                cutoffs["messages"],
                count=self._messages.count_before,
                delete=self._messages.prune_before,
                dry_run=dry_run,
                budget=budget,
            ),
        }

        if self._coordination_requests is not None:
            # This protocol window is fixed, not shortened by admin overrides.
            # Unlike age-based cutoffs, this cutoff compares expires_at <= now.
            # Pending approvals also expire: integrating use cases must find
            # the original receipt in-window before admitting execution.
            windows["coordination_requests"] = RETENTION_DAYS
            cutoffs["coordination_requests_expires_at"] = now
            tables["coordination_requests"] = self._run_table(
                now, count=self._coordination_requests.count_expired,
                delete=self._coordination_requests.prune_expired,
                dry_run=dry_run, budget=budget)

        row_limits = {}
        if self._observations is not None:
            windows["observation_events"] = self._config.observation_event_retention_days
            cutoffs["observation_events"] = iso_plus(
                now, -windows["observation_events"] * _SECONDS_PER_DAY)
            row_limits["observation_events"] = self._config.observation_max_events
            tables["observation_events"] = self._run_table(
                cutoffs["observation_events"],
                count=partial(self._observations.count_prunable_events,
                              max_events=row_limits["observation_events"]),
                delete=partial(self._observations.prune_events,
                               max_events=row_limits["observation_events"]),
                dry_run=dry_run, budget=budget,
                batch_size=min(self._batch_size, OBSERVATION_PRUNE_BATCH_MAX))
            tables.update(self._run_observation_cleanup(now, dry_run=dry_run, budget=budget))

        vacuum_report = self._maybe_vacuum(requested=vacuum, dry_run=dry_run)

        return {
            "dry_run": bool(dry_run),
            "now": now,
            "windows_days": windows,
            "cutoffs": cutoffs,
            "row_limits": row_limits,
            "tables": tables,
            "total_deleted": sum(t["deleted"] for t in tables.values()),
            "protected": (
                "unread/delivered/parked deliveries and active/stale sessions "
                "are never pruned; all handoffs/tasks/channels/agents/"
                "workspaces/artifacts are never pruned. Messages ARE pruned by "
                "age (>= 7-day window), except runtime evidence and causal fences; taking unprotected deliveries and "
                "embeddings with them. Coordination references survive resource deletion "
                "until their fixed 30-day expiry; expired references are pruned in bounded batches. "
                "Registered external observation heads, sequence/hash fences and their publisher tokens "
                "are preserved; only unreferenced expired/revoked tokens and orphaned source/agent rate buckets "
                "are pruned. Installation and existing identity/source budgets are preserved"
            ),
            "vacuum": vacuum_report,
        }

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate_max_batches(max_batches: Any) -> int | None:
        if max_batches is None:
            return None
        if isinstance(max_batches, bool) or not isinstance(max_batches, int):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "max_batches must be a positive integer (per-table batch "
                "budget) or None to drain fully.",
                {"max_batches": max_batches},
            )
        if max_batches < 1:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "max_batches must be >= 1.",
                {"max_batches": max_batches},
            )
        return max_batches

    def _run_table(
        self,
        cutoff: str,
        *,
        count: Any,
        delete: Any,
        dry_run: bool,
        budget: int | None,
        batch_size: int | None = None,
    ) -> dict[str, Any]:
        """Prune (or count) ONE table; return ``{"deleted", "complete"}``.

        Dry-run is a single read-only snapshot (no writer lock). Real pruning
        loops bounded batches, EACH in its own write transaction so a long
        backlog never holds the WAL writer lock continuously; the loop ends
        when a batch comes back short (table drained -> ``complete=True``) or
        the budget runs out (``complete=False`` - backlog remains).
        """
        if dry_run:
            with self._cf.unit_of_work(write=False) as uow:
                return {"deleted": int(count(uow, cutoff=cutoff)), "complete": True}
        deleted = 0
        batches = 0
        size = self._batch_size if batch_size is None else batch_size
        while budget is None or batches < budget:
            with self._cf.unit_of_work() as uow:
                n = int(delete(uow, cutoff=cutoff, limit=size))
            deleted += n
            batches += 1
            if n < size:
                return {"deleted": deleted, "complete": True}
        return {"deleted": deleted, "complete": False}

    def _run_observation_cleanup(self, now, *, dry_run, budget):
        """Share one bounded batch budget across auxiliary tokens and buckets.

        Keep table counts flat in the ordinary retention report. The adapter's
        limit applies to tokens plus buckets together, not once per table.
        Finishing the budget uses one passive count to report each backlog.
        """
        repo = self._observations
        if dry_run:
            with self._cf.unit_of_work(write=False) as uow:
                counts = repo.count_prunable(uow, now=now)
            return {"observation_" + key: {"deleted": int(counts[key]), "complete": True}
                    for key in ("tokens", "rate_buckets")}
        deleted = {"tokens": 0, "rate_buckets": 0}
        size = min(self._batch_size, OBSERVATION_PRUNE_BATCH_MAX)
        batches = 0
        while budget is None or batches < budget:
            with self._cf.unit_of_work() as uow:
                counts = repo.prune(uow, now=now, limit=size)
            for key in deleted:
                deleted[key] += int(counts[key])
            batches += 1
            if sum(counts.values()) < size:
                return {"observation_" + key: {"deleted": count, "complete": True}
                        for key, count in deleted.items()}
        with self._cf.unit_of_work(write=False) as uow:
            remaining = repo.count_prunable(uow, now=now)
        return {"observation_" + key: {"deleted": count, "complete": remaining[key] == 0}
                for key, count in deleted.items()}

    def _maybe_vacuum(self, *, requested: bool, dry_run: bool) -> dict[str, Any]:
        """Run ``VACUUM`` when requested on a real prune; report what happened.

        ``vacuum`` reclaims file space only on a REAL prune (a dry run frees
        nothing, so compacting would be misleading); the capability lives on
        the connection factory adapter - a factory without it fails closed
        with a prescriptive error instead of silently skipping.
        """
        if not requested:
            return {"requested": False, "ran": False, "skipped_reason": None}
        if dry_run:
            return {
                "requested": True,
                "ran": False,
                "skipped_reason": (
                    "dry_run deletes nothing, so there is nothing to compact; "
                    "re-run without --dry-run to prune and vacuum"
                ),
            }
        vacuum_fn = getattr(self._cf, "vacuum", None)
        if not callable(vacuum_fn):
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "This connection factory does not support vacuum(); wire the "
                "SQLite ConnectionFactory (adapters.outbound.sqlite.connection)"
                " or call prune without vacuum=True.",
                {"connection_factory": type(self._cf).__name__},
            )
        vacuum_fn()
        return {"requested": True, "ran": True, "skipped_reason": None}
