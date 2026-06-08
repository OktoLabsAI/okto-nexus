"""Handoff lifecycle application service.

Implements the use cases of Okto Nexus V1 spec #8:

* ``handoff_create``         - validate target/visibility + content limit, persist
  an ``OPEN`` handoff, emit ``handoff.created``.
* ``handoff_list_available`` - run opportunistic lease expiry, then return the
  ``OPEN`` handoffs that are BOTH visible AND eligible to the caller, paginated
  (``next_cursor``/``has_more``/``timed_out``), with optional long-poll.
* ``handoff_claim``          - opportunistic expiry + atomic conditional claim
  (single winner) gated by ``is_agent_eligible``.
* ``handoff_complete``       - owner-only ``CLAIMED -> COMPLETED``.
* ``handoff_reject``         - owner ``CLAIMED -> REJECTED`` or direct-target
  ``OPEN -> REJECTED``.

This module lives in the application layer: it depends only on the ports in
:mod:`okto_nexus.application.ports`, the pure :mod:`okto_nexus.domain` helpers
(state machine + imported routing/eligibility), the error catalogue and
:class:`NexusConfig`. It NEVER imports ``sqlite3`` nor ``mcp`` (enforced by the
import-boundary test). Every state mutation and its lifecycle event commit
atomically inside a single unit of work.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ..config import NexusConfig
from ..domain.base import new_id, utf8_byte_len
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
from ..errors import ErrorCode, OktoNexusError
from .ports import (
    AgentRepo,
    Clock,
    ConnectionFactory,
    EventEmitter,
    HandoffRepo,
    TaskRepo,
    UnitOfWork,
)

#: Default page size for ``handoff_list_available`` when no ``limit`` is given.
DEFAULT_PAGE_LIMIT = 100
#: Hard upper bound on a single page (defensive; keeps responses bounded).
MAX_PAGE_LIMIT = 500


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _iso_to_epoch(iso: str) -> float:
    """Parse a UTC ISO-8601 timestamp (``...Z`` or ``+00:00``) to POSIX epoch."""
    text = iso.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _epoch_to_iso(epoch: float) -> str:
    """Render a POSIX epoch as a UTC ISO-8601 string with a ``Z`` suffix."""
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


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
    ) -> None:
        self._cf = connection_factory
        self._handoffs = handoffs
        self._tasks = tasks
        self._clock = clock
        self._config = config
        self._emitter = event_emitter
        self._agents = agents

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
                created_at=now,
            )
            event_payload: dict[str, Any] = {
                "handoff_id": handoff.handoff_id,
                "workspace_id": handoff.workspace_id,
                "status": handoff.status,
                "from_agent_id": handoff.from_agent_id,
                "target": normalized_target,
                "visibility": handoff.visibility,
                "created_at": handoff.created_at,
            }
            if payload is not None:
                event_payload["payload"] = payload
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
        (bounded by ``config.max_wait_timeout_seconds``, polling every
        ``config.poll_interval_ms``) until a handoff appears or the deadline is
        reached (``timed_out=True``).
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
        poll_interval = max(self._config.poll_interval_ms, 1) / 1000.0
        deadline = time.monotonic() + timeout if timeout > 0 else None

        while True:
            now = self._clock.now_iso()
            with self._cf.unit_of_work() as uow:
                agent = self._routing_agent(uow, agent_id, workspace_id)
                available = self._available_handoffs(uow, workspace_id, agent, now)
            page = available[offset : offset + page_limit]
            has_more = (offset + len(page)) < len(available)
            if page or timeout <= 0:
                return self._list_response(page, offset, has_more, timed_out=False)
            if deadline is None or time.monotonic() >= deadline:
                return self._list_response(page, offset, has_more, timed_out=True)
            time.sleep(poll_interval)

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
        lease_expires_at = _epoch_to_iso(_iso_to_epoch(now) + lease_ttl)

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
        when the source state is not ``CLAIMED``.
        """
        workspace_id = self._resolve_workspace(project_root)
        self._require_id("handoff_id", handoff_id)
        self._require_id("agent_id", agent_id)
        self._check_inline_size("result", result)
        now = self._clock.now_iso()

        with self._cf.unit_of_work() as uow:
            handoff = self._load_in_workspace(uow, workspace_id, handoff_id)
            if handoff.status != STATUS_CLAIMED:
                raise OktoNexusError(
                    ErrorCode.INVALID_TRANSITION,
                    "handoff_complete requires the handoff to be CLAIMED.",
                    {"handoff_id": handoff_id, "status": handoff.status},
                )
            if handoff.claimed_by != agent_id:
                raise OktoNexusError(
                    ErrorCode.NOT_OWNER,
                    "Only the claim owner may complete this handoff.",
                    {"handoff_id": handoff_id, "agent_id": agent_id},
                )
            updated = self._handoffs.update_status(
                uow,
                workspace_id=workspace_id,
                handoff_id=handoff_id,
                status=STATUS_COMPLETED,
                updated_at=now,
            )
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
        source state gets ``INVALID_TRANSITION``.
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
                        {"handoff_id": handoff_id, "agent_id": agent_id},
                    )
            elif handoff.status == STATUS_OPEN:
                if not is_direct_target(handoff.target, agent_id):
                    raise OktoNexusError(
                        ErrorCode.NOT_OWNER,
                        "Only the direct target may reject an OPEN handoff.",
                        {"handoff_id": handoff_id, "agent_id": agent_id},
                    )
            else:
                raise OktoNexusError(
                    ErrorCode.INVALID_TRANSITION,
                    "handoff cannot be rejected from its current state.",
                    {"handoff_id": handoff_id, "status": handoff.status},
                )
            updated = self._handoffs.update_status(
                uow,
                workspace_id=workspace_id,
                handoff_id=handoff_id,
                status=STATUS_REJECTED,
                updated_at=now,
            )
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
        now_epoch = _iso_to_epoch(now_iso)
        expired: list[str] = []
        for handoff in self._handoffs.list(
            uow, workspace_id=workspace_id, status=STATUS_CLAIMED
        ):
            if not handoff.lease_expires_at:
                continue
            try:
                lease_epoch = _iso_to_epoch(handoff.lease_expires_at)
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
        if cursor is None or (isinstance(cursor, str) and not cursor.strip()):
            return 0
        try:
            value = int(str(cursor).strip())
        except (TypeError, ValueError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "cursor must be a non-negative integer.",
                {"cursor": cursor},
            ) from None
        if value < 0:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "cursor must be a non-negative integer.",
                {"cursor": cursor},
            )
        return value

    def _parse_limit(self, limit: Any) -> int:
        if limit is None or (isinstance(limit, str) and not str(limit).strip()):
            return DEFAULT_PAGE_LIMIT
        if isinstance(limit, bool):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "limit must be a positive integer.",
                {"limit": limit},
            )
        try:
            value = int(str(limit).strip()) if isinstance(limit, str) else int(limit)
        except (TypeError, ValueError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "limit must be a positive integer.",
                {"limit": limit},
            ) from None
        if value <= 0:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "limit must be a positive integer.",
                {"limit": limit},
            )
        return min(value, MAX_PAGE_LIMIT)

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
        """Enforce the inclusive 64KB UTF-8 inline content limit."""
        if value is None:
            return
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError) as exc:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"{field} is not JSON-serialisable.",
                    {"field": field},
                ) from exc
        limit = self._config.max_inline_bytes
        if utf8_byte_len(text) > limit:
            raise OktoNexusError(
                ErrorCode.CONTENT_TOO_LARGE,
                f"{field} inline content exceeds {limit} UTF-8 bytes.",
                {"field": field, "max_inline_bytes": limit},
            )

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
