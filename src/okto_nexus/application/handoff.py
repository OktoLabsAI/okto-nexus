"""Handoff lifecycle application service.

Implements the use cases of Okto Nexus V1 spec #8:

* ``handoff_create``         - validate target/visibility + content limit, persist
  an ``OPEN`` handoff, emit ``handoff.created``.
* ``handoff_list_available`` - run opportunistic lease expiry, then return the
  ``OPEN`` handoffs that are BOTH visible AND eligible to the caller, paginated
  (``next_cursor``/``has_more``/``timed_out``), with optional long-poll. The
  long-poll blocks via the :class:`Waiter` port and re-scans ONLY when the
  waiter reports a store change OR a time-driven boundary is reached (a lease
  expiring, a ``direct_with_fallback`` target opening to its fallback pool) -
  never once per poll interval.
* ``handoff_claim``          - opportunistic expiry + atomic conditional claim
  (single winner) gated by ``is_agent_eligible``.
* ``handoff_complete``       - owner-only ``CLAIMED -> COMPLETED``.
* ``handoff_reject``         - owner ``CLAIMED -> REJECTED`` or direct-target
  ``OPEN -> REJECTED``.

``handoff_complete``/``handoff_reject`` mutate via CONDITIONAL updates that
mirror the claim (the WHERE clause re-asserts the expected status and
claimant); a 0-row outcome is re-read and mapped to the precise catalogue
error (already terminal? lease expired and reopened? different claimant?).

This module lives in the application layer: it depends only on the ports in
:mod:`okto_nexus.application.ports`, the pure :mod:`okto_nexus.domain` helpers
(state machine + imported routing/eligibility), the error catalogue and
:class:`NexusConfig`. It NEVER imports ``sqlite3`` nor ``mcp`` (enforced by the
import-boundary test). Every state mutation and its lifecycle event commit
atomically inside a single unit of work.
"""

from __future__ import annotations

import json
from typing import Any, Iterator, Mapping, Optional, Sequence

from ..config import NexusConfig
from ..domain.base import (
    check_inline_size,
    clamp_limit,
    iso_plus,
    iso_to_epoch,
    new_id,
    normalize_cursor,
)
from ..domain.handoff import (
    EVENT_CLAIMED,
    EVENT_COMPLETED,
    EVENT_CREATED,
    EVENT_EXPIRED,
    EVENT_REJECTED,
    HANDOFF_STREAM,
    STATUS_CLAIMED,
    STATUS_COMPLETED,
    STATUS_OPEN,
    STATUS_REJECTED,
    TERMINAL_STATUSES,
    is_direct_target,
    normalize_visibility,
    validate_target,
)
from ..domain.ids import resolve_workspace_id
from ..domain.routing import RoutingAgent, can_agent_see_event, is_agent_eligible
from ..domain.targets import normalize_strategy
from ..errors import ErrorCode, OktoNexusError
from .ports import (
    AgentRepo,
    Clock,
    ConnectionFactory,
    EventEmitter,
    HandoffRepo,
    TaskRepo,
    UnitOfWork,
    Waiter,
)

#: Default page size for ``handoff_list_available`` when no ``limit`` is given.
DEFAULT_PAGE_LIMIT = 100
#: Hard upper bound on a single page (defensive; keeps responses bounded).
MAX_PAGE_LIMIT = 500


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


class HandoffService:
    """Use-case orchestration for the handoff lifecycle."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        handoffs: HandoffRepo,
        tasks: TaskRepo,
        clock: Clock,
        config: NexusConfig,
        event_emitter: Optional[EventEmitter] = None,
        agents: Optional[AgentRepo] = None,
        waiter: Optional[Waiter] = None,
    ) -> None:
        self._cf = connection_factory
        self._handoffs = handoffs
        self._tasks = tasks
        self._clock = clock
        self._config = config
        self._emitter = event_emitter
        self._agents = agents
        # Blocking seam for the list_available long-poll: an injected Waiter
        # (deterministic in tests), or the store's own change waiter.
        self._waiter = waiter if waiter is not None else connection_factory.change_waiter()

    # ------------------------------------------------------------------ #
    # create
    # ------------------------------------------------------------------ #
    def handoff_create(
        self,
        *,
        project_root: Any,
        from_agent_id: Any,
        target: Any,
        visibility: Any,
        payload: Any = None,
        session_id: Any = None,
        task_id: Any = None,
    ) -> dict[str, Any]:
        """Create an ``OPEN`` handoff and emit ``handoff.created`` atomically.

        Raises ``WORKSPACE_REQUIRED``/``WORKSPACE_UNRESOLVED`` for workspace
        resolution, ``VALIDATION_ERROR`` for a missing ``from_agent_id`` or an
        invalid target/visibility, ``CONTENT_TOO_LARGE`` for an oversized inline
        payload, and ``NOT_FOUND`` for a referenced ``task_id`` that is absent.
        """
        workspace_id = self._resolve_workspace(project_root)
        if not _is_nonempty_str(from_agent_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "from_agent_id is required.",
                {"from_agent_id": from_agent_id},
            )
        normalized_target = validate_target(target)
        normalized_visibility = normalize_visibility(visibility)
        self._check_inline_size("payload", payload)
        payload_text = self._serialize_payload(payload)

        target_text = json.dumps(normalized_target, ensure_ascii=False)
        now = self._clock.now_iso()
        handoff_id = new_id("hof")

        with self._cf.unit_of_work() as uow:
            if task_id is not None and _is_nonempty_str(task_id):
                if self._tasks.get(uow, workspace_id=workspace_id, task_id=task_id) is None:
                    raise OktoNexusError(
                        ErrorCode.NOT_FOUND,
                        "task_id does not exist in this workspace.",
                        {"task_id": task_id},
                    )
            handoff = self._handoffs.create(
                uow,
                handoff_id=handoff_id,
                workspace_id=workspace_id,
                status=STATUS_OPEN,
                task_id=task_id if _is_nonempty_str(task_id) else None,
                from_agent_id=from_agent_id,
                target=target_text,
                visibility=normalized_visibility,
                payload=payload_text,
                created_at=now,
            )
            self._touch_agent(uow, from_agent_id, now)
            event_payload: dict[str, Any] = {
                "handoff_id": handoff.handoff_id,
                "workspace_id": handoff.workspace_id,
                "status": handoff.status,
                "from_agent_id": handoff.from_agent_id,
                "target": normalized_target,
                "visibility": handoff.visibility,
                "created_at": handoff.created_at,
            }
            # Emit the SERIALISED payload (the same TEXT stored on the row), so
            # the handoff.created event, the stored row, and the
            # list_available/claim echo all expose ONE consistent representation
            # (a non-string payload would otherwise be an object on the event but
            # a JSON string on claim).
            if payload_text is not None:
                event_payload["payload"] = payload_text
            if _is_nonempty_str(session_id):
                event_payload["session_id"] = session_id
            self._emit(
                uow,
                handoff=handoff,
                event_type=EVENT_CREATED,
                actor_agent_id=from_agent_id,
                payload=event_payload,
            )
        return {
            "handoff_id": handoff.handoff_id,
            "workspace_id": handoff.workspace_id,
            "status": STATUS_OPEN,
            "created_at": handoff.created_at,
        }

    # ------------------------------------------------------------------ #
    # list_available
    # ------------------------------------------------------------------ #
    def handoff_list_available(
        self,
        *,
        project_root: Any,
        agent_id: Any,
        cursor: Any = None,
        limit: Any = None,
        timeout_seconds: Any = None,
    ) -> dict[str, Any]:
        """List the OPEN, visible AND eligible handoffs for ``agent_id``.

        Runs ``expire_old_leases`` first (opportunistic), then filters by
        :func:`can_agent_see_event` AND :func:`is_agent_eligible`. The result is
        paginated with ``next_cursor``/``has_more``/``timed_out``. When
        ``timeout_seconds`` is positive and the page is empty, the call blocks
        (bounded by ``config.max_wait_timeout_seconds``) until a handoff
        appears or the deadline is reached (``timed_out=True``). Blocking goes
        through the :class:`Waiter` port and the scan is re-run ONLY when

        * the waiter reports a store change (a commit by any process), or
        * the next TIME-DRIVEN boundary arrives - the earliest pending lease
          expiry (a reopen needs no write until this scan performs it) or
          ``direct_with_fallback`` opening (eligibility widens with no write);
          see :meth:`_next_wake_epoch`.
        """
        workspace_id = self._resolve_workspace(project_root)
        if not _is_nonempty_str(agent_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "agent_id is required.",
                {"agent_id": agent_id},
            )
        offset = self._parse_cursor(cursor)
        page_limit = self._parse_limit(limit)
        timeout = self._clamp_timeout(timeout_seconds)
        waiter = self._waiter
        # Floor for boundary waits: a boundary sitting exactly on ``now``
        # (e.g. a lease at the strict-expiry edge) re-scans at poll cadence
        # instead of busy-looping.
        poll_floor_s = max(self._config.poll_interval_ms, 1) / 1000.0
        # Snapshot precedes the first scan (Waiter contract): a write landing
        # between the scan and the wait wakes the first wait_for_change.
        token = waiter.snapshot() if timeout > 0 else None
        deadline = waiter.monotonic() + timeout if timeout > 0 else None

        while True:
            now = self._clock.now_iso()
            with self._cf.unit_of_work() as uow:
                agent = self._routing_agent(uow, agent_id, workspace_id)
                available = self._available_handoffs(uow, workspace_id, agent, now)
            page = available[offset : offset + page_limit]
            has_more = (offset + len(page)) < len(available)
            if page or timeout <= 0:
                return self._list_response(page, offset, has_more, timed_out=False)
            remaining = deadline - waiter.monotonic()
            if remaining <= 0:
                return self._list_response(page, offset, has_more, timed_out=True)
            wait_s = remaining
            next_wake = self._next_wake_epoch(workspace_id, now)
            if next_wake is not None:
                until_boundary = max(next_wake - iso_to_epoch(now), poll_floor_s)
                wait_s = min(remaining, until_boundary)
            changed = waiter.wait_for_change(token, wait_s)
            if not changed and wait_s >= remaining:
                # Full remaining window, no commit anywhere and no boundary
                # pending: a re-scan provably finds the same empty page.
                return self._list_response(page, offset, has_more, timed_out=True)
            # Otherwise re-scan: a write happened, or a time boundary was
            # reached (lease expiry / fallback opening processed by the scan).
            token = waiter.snapshot()

    def _available_handoffs(
        self, uow: UnitOfWork, workspace_id: str, agent: RoutingAgent, now: str
    ) -> list[Any]:
        """Expire stale leases, then return the OPEN visible+eligible handoffs."""
        self._expire_old_leases(uow, workspace_id=workspace_id, now_iso=now)
        rows = self._handoffs.list(uow, workspace_id=workspace_id, status=STATUS_OPEN)
        visible = [
            h
            for h in rows
            if can_agent_see_event(agent, h, now)
            and is_agent_eligible(agent, h.target, h.created_at, now)
        ]
        visible.sort(key=lambda h: (h.created_at or "", h.handoff_id))
        return visible

    def _next_wake_epoch(self, workspace_id: str, now_iso: str) -> float | None:
        """Earliest FUTURE instant the available set can change WITHOUT a write.

        Two boundaries are time-driven (so ``data_version`` alone would sleep
        through them):

        * a CLAIMED lease expiring - the next scan reopens it (strict
          ``lease_expires_at < now``, so the boundary is the lease instant
          itself, re-checked at poll cadence until strictly past);
        * a ``direct_with_fallback`` target (possibly nested under ``mixed``
          rules or a ``fallback`` sub-target) reaching
          ``created_at + fallback_after_seconds`` - eligibility widens to the
          fallback pool with no write.

        Returns ``None`` when no boundary is pending. Read-only (own deferred
        snapshot; never competes for the WAL writer lock) and defensive: a row
        with a malformed timestamp/target can never break the wait - it is
        skipped (the write path already validates, so this is row-level
        hardening, not policy).
        """
        now_epoch = iso_to_epoch(now_iso)
        candidates: list[float] = []
        with self._cf.unit_of_work(write=False) as uow:
            for handoff in self._handoffs.list(
                uow, workspace_id=workspace_id, status=STATUS_CLAIMED
            ):
                if not handoff.lease_expires_at:
                    continue
                try:
                    lease_epoch = iso_to_epoch(handoff.lease_expires_at)
                except (TypeError, ValueError):
                    continue
                if lease_epoch >= now_epoch:
                    candidates.append(lease_epoch)
            for handoff in self._handoffs.list(
                uow, workspace_id=workspace_id, status=STATUS_OPEN
            ):
                if not handoff.created_at:
                    continue
                try:
                    created_epoch = iso_to_epoch(handoff.created_at)
                    target = _loads_target(handoff.target)
                    for boundary in _fallback_boundaries(target, created_epoch):
                        if boundary > now_epoch:
                            candidates.append(boundary)
                except (TypeError, ValueError, OktoNexusError):
                    continue
        return min(candidates) if candidates else None

    def _list_response(
        self, page: list[Any], offset: int, has_more: bool, *, timed_out: bool
    ) -> dict[str, Any]:
        return {
            "handoffs": [self._serialize_available(h) for h in page],
            "next_cursor": str(offset + len(page)) if has_more else None,
            "has_more": has_more,
            "timed_out": timed_out,
        }

    @staticmethod
    def _serialize_available(handoff: Any) -> dict[str, Any]:
        return {
            "handoff_id": handoff.handoff_id,
            "status": handoff.status,
            "target": _loads_target(handoff.target),
            "visibility": handoff.visibility,
            "from_agent_id": handoff.from_agent_id,
            "payload": handoff.payload,
            "created_at": handoff.created_at,
        }

    # ------------------------------------------------------------------ #
    # claim
    # ------------------------------------------------------------------ #
    def handoff_claim(
        self,
        *,
        project_root: Any,
        handoff_id: Any,
        agent_id: Any,
        session_id: Any = None,
    ) -> dict[str, Any]:
        """Atomically claim an OPEN handoff (single winner).

        Expires stale leases first, gates on :func:`is_agent_eligible`
        (``NOT_ELIGIBLE_TO_CLAIM``), then runs the atomic conditional UPDATE.
        Zero affected rows map to ``HANDOFF_ALREADY_CLAIMED`` /
        ``WORKSPACE_MISMATCH`` / ``NOT_FOUND`` with no event emitted.
        """
        workspace_id = self._resolve_workspace(project_root)
        self._require_id("handoff_id", handoff_id)
        self._require_id("agent_id", agent_id)
        now = self._clock.now_iso()
        lease_ttl = int(self._config.handoff_lease_ttl_seconds)
        # iso_plus is the lease-WRITE boundary: it rejects a non-canonical
        # (non-lexicographically-comparable) clock value and always emits the
        # fixed-width form.
        lease_expires_at = iso_plus(now, lease_ttl)

        with self._cf.unit_of_work() as uow:
            self._expire_old_leases(uow, workspace_id=workspace_id, now_iso=now)
            handoff = self._load_in_workspace(uow, workspace_id, handoff_id)

            agent = self._routing_agent(uow, agent_id, workspace_id)
            if not is_agent_eligible(agent, handoff.target, handoff.created_at, now):
                raise OktoNexusError(
                    ErrorCode.NOT_ELIGIBLE_TO_CLAIM,
                    "Agent is not eligible to claim this handoff.",
                    {"handoff_id": handoff_id, "agent_id": agent_id},
                )

            claimed = self._handoffs.claim(
                uow,
                workspace_id=workspace_id,
                handoff_id=handoff_id,
                claimed_by=agent_id,
                lease_expires_at=lease_expires_at,
                updated_at=now,
            )
            self._touch_agent(uow, agent_id, now)
            payload = {
                "handoff_id": claimed.handoff_id,
                "workspace_id": claimed.workspace_id,
                "status": claimed.status,
                "claimed_by": claimed.claimed_by,
                "lease_expires_at": claimed.lease_expires_at,
            }
            if _is_nonempty_str(session_id):
                payload["claimed_session_id"] = session_id
            self._emit(
                uow,
                handoff=claimed,
                event_type=EVENT_CLAIMED,
                actor_agent_id=agent_id,
                payload=payload,
            )
        return {
            "handoff_id": claimed.handoff_id,
            "workspace_id": claimed.workspace_id,
            "status": STATUS_CLAIMED,
            "claimed_by": claimed.claimed_by,
            "lease_expires_at": claimed.lease_expires_at,
            "payload": claimed.payload,
        }

    # ------------------------------------------------------------------ #
    # complete
    # ------------------------------------------------------------------ #
    def handoff_complete(
        self,
        *,
        project_root: Any,
        handoff_id: Any,
        agent_id: Any,
        result: Any = None,
    ) -> dict[str, Any]:
        """Owner-only ``CLAIMED -> COMPLETED``.

        ``NOT_OWNER`` when ``agent_id != claimed_by``; ``INVALID_TRANSITION``
        when the source state is not ``CLAIMED``. The mutation is a single
        conditional UPDATE (mirrors the claim); a 0-row outcome is re-read and
        mapped to the precise error.
        """
        workspace_id = self._resolve_workspace(project_root)
        self._require_id("handoff_id", handoff_id)
        self._require_id("agent_id", agent_id)
        self._check_inline_size("result", result)
        now = self._clock.now_iso()

        with self._cf.unit_of_work() as uow:
            updated = self._handoffs.transition_claimed(
                uow,
                workspace_id=workspace_id,
                handoff_id=handoff_id,
                claimed_by=agent_id,
                status=STATUS_COMPLETED,
                updated_at=now,
            )
            if updated is None:
                self._raise_claimed_transition_error(
                    uow, workspace_id, handoff_id, agent_id, verb="complete"
                )
            self._touch_agent(uow, agent_id, now)
            payload = {
                "handoff_id": updated.handoff_id,
                "workspace_id": updated.workspace_id,
                "status": updated.status,
            }
            if result is not None:
                payload["result"] = result
            self._emit(
                uow,
                handoff=updated,
                event_type=EVENT_COMPLETED,
                actor_agent_id=agent_id,
                payload=payload,
            )
        return {"handoff_id": updated.handoff_id, "status": STATUS_COMPLETED}

    # ------------------------------------------------------------------ #
    # reject
    # ------------------------------------------------------------------ #
    def handoff_reject(
        self,
        *,
        project_root: Any,
        handoff_id: Any,
        agent_id: Any,
        reason: Any = None,
    ) -> dict[str, Any]:
        """Reject a handoff.

        The claim owner transitions ``CLAIMED -> REJECTED``; a ``direct`` target
        may transition an unclaimed ``OPEN -> REJECTED``. A caller that is
        neither owner nor direct target gets ``NOT_OWNER``; a terminal/invalid
        source state gets ``INVALID_TRANSITION``. Both branches mutate via a
        conditional UPDATE that re-asserts the state read above (the read and
        the update share one IMMEDIATE transaction, and a 0-row outcome still
        maps to a precise error rather than clobbering the row).
        """
        workspace_id = self._resolve_workspace(project_root)
        self._require_id("handoff_id", handoff_id)
        self._require_id("agent_id", agent_id)
        self._check_inline_size("reason", reason)
        now = self._clock.now_iso()

        with self._cf.unit_of_work() as uow:
            handoff = self._load_in_workspace(uow, workspace_id, handoff_id)
            if handoff.status in TERMINAL_STATUSES:
                raise OktoNexusError(
                    ErrorCode.INVALID_TRANSITION,
                    "Terminal handoff cannot be rejected.",
                    {"handoff_id": handoff_id, "status": handoff.status},
                )
            if handoff.status == STATUS_CLAIMED:
                if handoff.claimed_by != agent_id:
                    raise OktoNexusError(
                        ErrorCode.NOT_OWNER,
                        "Only the claim owner may reject a CLAIMED handoff.",
                        {
                            "handoff_id": handoff_id,
                            "agent_id": agent_id,
                            "claimed_by": handoff.claimed_by,
                        },
                    )
                updated = self._handoffs.transition_claimed(
                    uow,
                    workspace_id=workspace_id,
                    handoff_id=handoff_id,
                    claimed_by=agent_id,
                    status=STATUS_REJECTED,
                    updated_at=now,
                )
            elif handoff.status == STATUS_OPEN:
                if not is_direct_target(handoff.target, agent_id):
                    raise OktoNexusError(
                        ErrorCode.NOT_OWNER,
                        "Only the direct target may reject an OPEN handoff.",
                        {"handoff_id": handoff_id, "agent_id": agent_id},
                    )
                updated = self._handoffs.reject_open(
                    uow,
                    workspace_id=workspace_id,
                    handoff_id=handoff_id,
                    updated_at=now,
                )
            else:
                raise OktoNexusError(
                    ErrorCode.INVALID_TRANSITION,
                    "handoff cannot be rejected from its current state.",
                    {"handoff_id": handoff_id, "status": handoff.status},
                )
            if updated is None:  # pragma: no cover - unreachable: the read and
                # the UPDATE share one BEGIN IMMEDIATE transaction, so the row
                # cannot change in between; kept as defence in depth.
                self._raise_claimed_transition_error(
                    uow, workspace_id, handoff_id, agent_id, verb="reject"
                )
            self._touch_agent(uow, agent_id, now)
            payload = {
                "handoff_id": updated.handoff_id,
                "workspace_id": updated.workspace_id,
                "status": updated.status,
            }
            if _is_nonempty_str(reason):
                payload["reason"] = reason
            self._emit(
                uow,
                handoff=updated,
                event_type=EVENT_REJECTED,
                actor_agent_id=agent_id,
                payload=payload,
            )
        return {"handoff_id": updated.handoff_id, "status": STATUS_REJECTED}

    # ------------------------------------------------------------------ #
    # Opportunistic lease expiry
    # ------------------------------------------------------------------ #
    def expire_old_leases(self, *, project_root: Any) -> dict[str, Any]:
        """Public entry point to expire stale leases for a workspace.

        Primarily an internal routine invoked before list/claim, exposed here
        for completeness/testing. Returns the list of reopened handoff ids.
        """
        workspace_id = self._resolve_workspace(project_root)
        now = self._clock.now_iso()
        with self._cf.unit_of_work() as uow:
            expired = self._expire_old_leases(uow, workspace_id=workspace_id, now_iso=now)
        return {"workspace_id": workspace_id, "expired": expired}

    def _expire_old_leases(
        self, uow: UnitOfWork, *, workspace_id: str, now_iso: str
    ) -> list[str]:
        """Reopen every CLAIMED handoff whose lease strictly expired before now.

        Strict threshold: ``lease_expires_at < now`` expires; ``== now`` does
        not. Each successful reopen emits ``handoff.expired`` in the same
        transaction. Returns the reopened handoff ids.
        """
        now_epoch = iso_to_epoch(now_iso)
        expired: list[str] = []
        for handoff in self._handoffs.list(
            uow, workspace_id=workspace_id, status=STATUS_CLAIMED
        ):
            if not handoff.lease_expires_at:
                continue
            try:
                lease_epoch = iso_to_epoch(handoff.lease_expires_at)
            except (ValueError, TypeError):
                continue
            if lease_epoch >= now_epoch:  # strict: == now does NOT expire
                continue
            reopened = self._handoffs.reopen_expired(
                uow,
                workspace_id=workspace_id,
                handoff_id=handoff.handoff_id,
                updated_at=now_iso,
            )
            if reopened is None:
                continue
            self._emit(
                uow,
                handoff=reopened,
                event_type=EVENT_EXPIRED,
                actor_agent_id=None,
                payload={
                    "handoff_id": reopened.handoff_id,
                    "workspace_id": reopened.workspace_id,
                    "status": reopened.status,
                    "previous_claimed_by": handoff.claimed_by,
                },
            )
            expired.append(reopened.handoff_id)
        return expired

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _resolve_workspace(self, project_root: Any) -> str:
        if not _is_nonempty_str(project_root):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_REQUIRED,
                "project_root (workspace_id) is required for handoff operations.",
                {},
            )
        # resolve_workspace_id raises WORKSPACE_UNRESOLVED for irresolvable paths.
        return resolve_workspace_id(project_root)

    def _touch_agent(self, uow: UnitOfWork, agent_id: Any, now: str) -> None:
        """Best-effort stamp of the actor's ``last_seen_at`` within ``uow``."""
        if self._agents is not None and _is_nonempty_str(agent_id):
            self._agents.touch(uow, agent_id=agent_id, at=now)

    @staticmethod
    def _require_id(field: str, value: Any) -> None:
        if not _is_nonempty_str(value):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} is required.",
                {field: value},
            )

    def _load_in_workspace(
        self, uow: UnitOfWork, workspace_id: str, handoff_id: str
    ) -> Any:
        """Load a handoff scoped to the workspace, mapping absence precisely.

        ``NOT_FOUND`` when the id exists nowhere; ``WORKSPACE_MISMATCH`` when it
        exists only in another workspace (no cross-workspace read).
        """
        handoff = self._handoffs.get(
            uow, workspace_id=workspace_id, handoff_id=handoff_id
        )
        if handoff is not None:
            return handoff
        if self._handoffs.exists_any_workspace(uow, handoff_id=handoff_id):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_MISMATCH,
                "handoff belongs to a different workspace.",
                {"handoff_id": handoff_id, "workspace_id": workspace_id},
            )
        raise OktoNexusError(
            ErrorCode.NOT_FOUND,
            "handoff_id does not exist.",
            {"handoff_id": handoff_id},
        )

    def _raise_claimed_transition_error(
        self,
        uow: UnitOfWork,
        workspace_id: str,
        handoff_id: str,
        agent_id: str,
        *,
        verb: str,
    ) -> None:
        """Map a failed conditional CLAIMED transition to the precise error.

        Called when the conditional UPDATE affected 0 rows. Re-reads the row in
        the same transaction: absence maps via :meth:`_load_in_workspace`
        (``NOT_FOUND``/``WORKSPACE_MISMATCH``); an OPEN row means the claim
        lease expired and reopened it; a terminal row was already finished; a
        CLAIMED row held by someone else is ``NOT_OWNER``. Always raises.
        """
        handoff = self._load_in_workspace(uow, workspace_id, handoff_id)
        if handoff.status == STATUS_OPEN:
            raise OktoNexusError(
                ErrorCode.INVALID_TRANSITION,
                f"handoff_{verb} requires the handoff to be CLAIMED, but it is "
                "OPEN - the claim lease may have expired and reopened it. Call "
                "handoff_claim again before retrying.",
                {"handoff_id": handoff_id, "status": handoff.status},
            )
        if handoff.status in TERMINAL_STATUSES:
            raise OktoNexusError(
                ErrorCode.INVALID_TRANSITION,
                f"handoff_{verb} requires the handoff to be CLAIMED, but it is "
                f"already {handoff.status}.",
                {"handoff_id": handoff_id, "status": handoff.status},
            )
        if handoff.claimed_by != agent_id:
            raise OktoNexusError(
                ErrorCode.NOT_OWNER,
                f"Only the claim owner may {verb} this handoff.",
                {
                    "handoff_id": handoff_id,
                    "agent_id": agent_id,
                    "claimed_by": handoff.claimed_by,
                },
            )
        raise OktoNexusError(  # pragma: no cover - defensive: the predicate
            # held on re-read, so the UPDATE could not have affected 0 rows.
            ErrorCode.INVALID_TRANSITION,
            f"handoff_{verb} failed; the current state does not allow it.",
            {"handoff_id": handoff_id, "status": handoff.status},
        )

    def _routing_agent(
        self, uow: UnitOfWork, agent_id: str, workspace_id: str
    ) -> RoutingAgent:
        """Build the routing view of the caller from the agent profile (if any)."""
        role: str | None = None
        capabilities: Any = None
        if self._agents is not None:
            profile = self._agents.get(uow, agent_id)
            if profile is not None:
                role = profile.role
                capabilities = profile.capabilities
        return RoutingAgent(
            agent_id=agent_id,
            workspace_id=workspace_id,
            role=role,
            capabilities=capabilities,
        )

    def _parse_cursor(self, cursor: Any) -> int:
        # Shared pagination grammar (domain.base): one cursor parser bus-wide.
        return normalize_cursor(cursor)

    def _parse_limit(self, limit: Any) -> int:
        # Shared pagination grammar (domain.base): one limit parser bus-wide.
        return clamp_limit(limit, default=DEFAULT_PAGE_LIMIT, maximum=MAX_PAGE_LIMIT)

    def _clamp_timeout(self, timeout_seconds: Any) -> float:
        if timeout_seconds is None:
            return 0.0
        if isinstance(timeout_seconds, bool):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "timeout_seconds must be a non-negative number.",
                {"timeout_seconds": timeout_seconds},
            )
        try:
            value = float(timeout_seconds)
        except (TypeError, ValueError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "timeout_seconds must be a non-negative number.",
                {"timeout_seconds": timeout_seconds},
            ) from None
        if value < 0:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "timeout_seconds must be a non-negative number.",
                {"timeout_seconds": timeout_seconds},
            )
        # Clamp to the configured maximum wait (seconds, not ms).
        return min(value, float(self._config.max_wait_timeout_seconds))

    def _check_inline_size(self, field: str, value: Any) -> None:
        """Enforce the inclusive 64KB UTF-8 inline content limit (shared helper)."""
        check_inline_size(field, value, self._config.max_inline_bytes)

    @staticmethod
    def _serialize_payload(payload: Any) -> str | None:
        """Serialise the inline payload to TEXT for storage (``None`` stays ``None``).

        A string is stored verbatim so it round-trips byte-for-byte back to the
        worker via ``handoff_list_available`` / ``handoff_claim``; any other
        JSON-serialisable value is encoded. The payload is treated as OPAQUE on
        read-back (returned as the stored TEXT, never re-parsed) - unlike
        ``target``, which is always a routing object and is echoed decoded.
        """
        if payload is None:
            return None
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False)

    def _emit(
        self,
        uow: UnitOfWork,
        *,
        handoff: Any,
        event_type: str,
        actor_agent_id: str | None,
        payload: Mapping[str, Any] | None,
    ) -> None:
        """Emit a handoff lifecycle event inside ``uow`` (skipped if unwired).

        ``event_id`` is owned/assigned by the Event Log slice (imported via the
        ``EventEmitter`` port), not redefined here.
        """
        if self._emitter is None:
            return
        self._emitter.emit(
            uow,
            workspace_id=handoff.workspace_id,
            stream=HANDOFF_STREAM,
            type=event_type,
            payload=dict(payload) if payload else None,
            actor_agent_id=actor_agent_id,
            visibility=handoff.visibility,
            target=handoff.target,
        )


def _loads_target(text: Any) -> Any:
    """Deserialise a stored target descriptor back into an object for responses."""
    if text is None:
        return None
    if isinstance(text, Mapping):
        return text
    if isinstance(text, str):
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return text
    return text


def _fallback_boundaries(target: Any, created_epoch: float) -> Iterator[float]:
    """Yield every instant ``target``'s eligible set can WIDEN with no write.

    Walks an already-stored (write-path-validated) target descriptor: each
    ``direct_with_fallback`` contributes ``created_epoch +
    fallback_after_seconds`` (the inclusive instant the fallback pool opens),
    recursing into ``mixed`` sub-rules and nested ``fallback`` sub-targets.
    Mirrors the time dependence of :func:`is_agent_eligible` - any strategy
    this yields nothing for is time-invariant. Raises ``VALIDATION_ERROR``
    only for an out-of-grammar strategy token (the caller skips that row).
    """
    if not isinstance(target, Mapping):
        return
    strategy = normalize_strategy(target.get("strategy", target.get("kind")))
    if strategy == "direct_with_fallback":
        after = target.get("fallback_after_seconds")
        if isinstance(after, (int, float)) and not isinstance(after, bool):
            yield created_epoch + float(after)
        fallback = target.get("fallback")
        if isinstance(fallback, Mapping):
            yield from _fallback_boundaries(fallback, created_epoch)
    elif strategy == "mixed":
        rules = target.get("rules", target.get("targets"))
        if isinstance(rules, Sequence) and not isinstance(rules, (str, bytes)):
            for rule in rules:
                yield from _fallback_boundaries(rule, created_epoch)
