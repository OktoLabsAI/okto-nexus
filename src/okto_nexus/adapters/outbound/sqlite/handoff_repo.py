"""SQLite repositories for the handoff lifecycle slice.

Concrete implementations of :class:`HandoffRepo` and :class:`TaskRepo` (from
:mod:`okto_nexus.application.ports`). Every method operates on
``uow.connection`` inside the caller's active transaction so the state mutation
and its lifecycle event commit atomically.

The atomic claim is a single conditional UPDATE
``... WHERE handoff_id=? AND status='OPEN' AND workspace_id=?`` whose affected
row count decides the outcome (1 => winner; 0 => reload + structured catalogue
error). There is NO SELECT-then-UPDATE on the claim winner path (no TOCTOU).
Terminal transitions mirror the same shape: :meth:`SqliteHandoffRepo.transition_claimed`
re-asserts ``status='CLAIMED' AND claimed_by=?`` and
:meth:`SqliteHandoffRepo.reject_open` re-asserts ``status='OPEN'`` in the WHERE
clause, so correctness comes from the row predicate - never from snapshot
isolation side effects.

This is an outbound adapter, so it may import ``sqlite3`` and the domain
dataclasses. The ``target`` descriptor is stored as a TEXT (JSON) string by the
application layer; this repo treats it opaquely.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from typing import Any, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.handoff import (
    STATUS_CLAIMED,
    STATUS_OPEN,
    STATUS_REJECTED,
    STATUS_VERIFYING,
    summarize_dependencies,
)
from ....domain.models import Handoff, Task
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


def _db_error(action: str, exc: sqlite3.Error) -> OktoNexusError:
    # Centralised classification: lock/busy contention => retryable=True.
    return db_error_from_exception(action, exc)


def dependency_aggregates_for(
    uow: UnitOfWork,
    *,
    workspace_id: str | None,
    handoff_ids: Iterable[str],
) -> dict[str, dict[str, Any]]:
    """Per-handoff dependency aggregates for a PAGE of ids, in ONE query.

    Returns ``{handoff_id: {"depends_on": [ids in creation order],
    "total", "satisfied", "pending", "failed"}}`` containing ONLY the ids
    that actually have dependency rows - callers treat a missing key as "no
    dependencies". Satisfaction is the strict domain rule
    (:func:`summarize_dependencies`); a dependency whose row has vanished
    (e.g. admin prune) counts as pending - it neither satisfies nor fails.

    Module-level so both :class:`SqliteHandoffRepo` and the observability
    read model share the single implementation (no N+1: one ``IN`` query per
    page). ``workspace_id`` of ``None`` skips the workspace filter (the
    observability read model's all-workspaces mode); dependency rows always
    join their own workspace's handoffs regardless.
    """
    ids = list(handoff_ids)
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    sql = (
        "SELECT d.handoff_id, d.depends_on_id, h.status "
        "FROM handoff_dependencies d "
        "LEFT JOIN handoffs h ON h.handoff_id = d.depends_on_id "
        "AND h.workspace_id = d.workspace_id "
        f"WHERE d.handoff_id IN ({placeholders})"
    )
    params: list[Any] = list(ids)
    if workspace_id is not None:
        sql += " AND d.workspace_id = ?"
        params.append(workspace_id)
    sql += " ORDER BY d.rowid"
    try:
        rows = uow.connection.execute(sql, tuple(params)).fetchall()
    except sqlite3.Error as exc:
        raise _db_error("aggregating handoff dependencies", exc) from exc
    depends_on: dict[str, list[str]] = {}
    statuses: dict[str, list[str]] = {}
    for row in rows:
        hid = row["handoff_id"]
        depends_on.setdefault(hid, []).append(row["depends_on_id"])
        statuses.setdefault(hid, []).append(row["status"] or "")
    return {
        hid: {"depends_on": deps, **summarize_dependencies(statuses[hid])}
        for hid, deps in depends_on.items()
    }


class _ClockBacked:
    """Mixin providing a ``_now`` timestamp from an optional injected clock."""

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock.now_iso()
        return utc_now_iso()


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #
class SqliteTaskRepo(_ClockBacked):
    """Persistence for ``tasks`` rows (workspace-scoped).

    DEAD in V1: the Task subsystem has no producer (no MCP tool creates a
    task and ``handoff_create`` no longer accepts ``task_id``). The class is
    kept ONLY because the server composition root (``server.py``) and the
    ``Repos`` registry (``application/ports.py``) still reference it; delete
    it together with that wiring.
    """

    _COLUMNS = (
        "task_id, workspace_id, title, description, status, created_by, created_at"
    )

    def create(
        self,
        uow: UnitOfWork,
        *,
        task_id: str,
        workspace_id: str,
        title: str,
        status: str,
        description: str | None = None,
        created_by: str | None = None,
        created_at: str | None = None,
    ) -> Task:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO tasks
                    (task_id, workspace_id, title, description, status, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, workspace_id, title, description, status, created_by, now),
            )
        except sqlite3.Error as exc:
            raise _db_error("creating task", exc) from exc
        row = self.get(uow, workspace_id=workspace_id, task_id=task_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Task missing immediately after insert.",
                {"task_id": task_id},
            )
        return row

    def get(self, uow: UnitOfWork, *, workspace_id: str, task_id: str) -> Task | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM tasks "
                "WHERE workspace_id = ? AND task_id = ?",
                (workspace_id, task_id),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading task", exc) from exc
        if row is None:
            return None
        return self._row_to_task(row)

    def update_status(
        self, uow: UnitOfWork, *, workspace_id: str, task_id: str, status: str
    ) -> Task:
        try:
            cur = uow.connection.execute(
                "UPDATE tasks SET status = ? WHERE workspace_id = ? AND task_id = ?",
                (status, workspace_id, task_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("updating task status", exc) from exc
        if cur.rowcount == 0:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "task_id does not exist in this workspace.",
                {"task_id": task_id, "workspace_id": workspace_id},
            )
        row = self.get(uow, workspace_id=workspace_id, task_id=task_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "task_id does not exist in this workspace.",
                {"task_id": task_id},
            )
        return row

    def list(
        self, uow: UnitOfWork, *, workspace_id: str, status: str | None = None
    ) -> list[Task]:
        sql = f"SELECT {self._COLUMNS} FROM tasks WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at, task_id"
        try:
            cur = uow.connection.execute(sql, tuple(params))
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing tasks", exc) from exc
        return [self._row_to_task(row) for row in rows]

    @staticmethod
    def _row_to_task(row: Any) -> Task:
        return Task(
            task_id=row["task_id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            status=row["status"],
            created_at=row["created_at"],
            description=row["description"],
            created_by=row["created_by"],
        )


# --------------------------------------------------------------------------- #
# Handoffs
# --------------------------------------------------------------------------- #
class SqliteHandoffRepo(_ClockBacked):
    """Persistence for ``handoffs`` rows, including atomic claim semantics."""

    _COLUMNS = (
        "handoff_id, workspace_id, task_id, from_agent_id, target, visibility, "
        "status, claimed_by, lease_expires_at, created_at, updated_at, payload, "
        "trace_id"
    )

    def create(
        self,
        uow: UnitOfWork,
        *,
        handoff_id: str,
        workspace_id: str,
        status: str,
        task_id: str | None = None,
        from_agent_id: str | None = None,
        target: str | None = None,
        visibility: str | None = None,
        payload: str | None = None,
        trace_id: str | None = None,
        acceptance_criteria: str | None = None,
        verify_by: str | None = None,
        created_at: str | None = None,
    ) -> Handoff:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO handoffs
                    (handoff_id, workspace_id, task_id, from_agent_id, target,
                     visibility, status, claimed_by, lease_expires_at,
                     created_at, updated_at, payload, trace_id,
                     acceptance_criteria, verify_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)
                """,
                (
                    handoff_id,
                    workspace_id,
                    task_id,
                    from_agent_id,
                    target,
                    visibility,
                    status,
                    now,
                    now,
                    payload,
                    trace_id,
                    acceptance_criteria,
                    verify_by,
                ),
            )
        except sqlite3.Error as exc:
            raise _db_error("creating handoff", exc) from exc
        row = self.get(uow, workspace_id=workspace_id, handoff_id=handoff_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Handoff missing immediately after insert.",
                {"handoff_id": handoff_id},
            )
        return row

    def get(
        self, uow: UnitOfWork, *, workspace_id: str, handoff_id: str
    ) -> Handoff | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM handoffs "
                "WHERE workspace_id = ? AND handoff_id = ?",
                (workspace_id, handoff_id),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading handoff", exc) from exc
        if row is None:
            return None
        return self._row_to_handoff(row)

    def exists_any_workspace(self, uow: UnitOfWork, *, handoff_id: str) -> bool:
        """Return whether a handoff with this id exists in ANY workspace.

        Used only to disambiguate ``NOT_FOUND`` from ``WORKSPACE_MISMATCH``; it
        never returns row contents across the workspace boundary.
        """
        try:
            cur = uow.connection.execute(
                "SELECT 1 FROM handoffs WHERE handoff_id = ? LIMIT 1",
                (handoff_id,),
            )
            return cur.fetchone() is not None
        except sqlite3.Error as exc:
            raise _db_error("checking handoff existence", exc) from exc

    def claim(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_id: str,
        claimed_by: str,
        lease_expires_at: str,
        updated_at: str | None = None,
    ) -> Handoff:
        """Atomically claim an OPEN handoff via a conditional UPDATE.

        Exactly one concurrent caller affects 1 row (the winner). On 0 rows the
        current state is reloaded and mapped to the structured catalogue error.
        """
        now = updated_at or self._now()
        try:
            cur = uow.connection.execute(
                """
                UPDATE handoffs
                   SET status = ?, claimed_by = ?, lease_expires_at = ?, updated_at = ?
                 WHERE handoff_id = ? AND status = ? AND workspace_id = ?
                """,
                (
                    STATUS_CLAIMED,
                    claimed_by,
                    lease_expires_at,
                    now,
                    handoff_id,
                    STATUS_OPEN,
                    workspace_id,
                ),
            )
        except sqlite3.Error as exc:
            raise _db_error("claiming handoff", exc) from exc

        if cur.rowcount == 1:
            row = self.get(uow, workspace_id=workspace_id, handoff_id=handoff_id)
            if row is None:  # pragma: no cover - defensive
                raise OktoNexusError(
                    ErrorCode.DB_ERROR,
                    "Handoff missing immediately after claim.",
                    {"handoff_id": handoff_id},
                )
            return row

        # 0 rows affected -> reload to classify the failure.
        existing = self.get(uow, workspace_id=workspace_id, handoff_id=handoff_id)
        if existing is not None:
            raise OktoNexusError(
                ErrorCode.HANDOFF_ALREADY_CLAIMED,
                "handoff is no longer OPEN (already claimed or transitioned).",
                {"handoff_id": handoff_id, "status": existing.status},
            )
        if self.exists_any_workspace(uow, handoff_id=handoff_id):
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

    def reopen_expired(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_id: str,
        updated_at: str | None = None,
    ) -> Handoff | None:
        """Atomically reopen a CLAIMED handoff (lease expired) back to OPEN.

        Clears ``claimed_by``/``lease_expires_at``. Returns the reopened row, or
        ``None`` when the conditional UPDATE affected 0 rows (already changed by
        a racing writer), in which case no event should be emitted.
        """
        now = updated_at or self._now()
        try:
            cur = uow.connection.execute(
                """
                UPDATE handoffs
                   SET status = ?, claimed_by = NULL, lease_expires_at = NULL,
                       updated_at = ?
                 WHERE handoff_id = ? AND workspace_id = ? AND status = ?
                """,
                (STATUS_OPEN, now, handoff_id, workspace_id, STATUS_CLAIMED),
            )
        except sqlite3.Error as exc:
            raise _db_error("reopening expired handoff", exc) from exc
        if cur.rowcount == 0:
            return None
        return self.get(uow, workspace_id=workspace_id, handoff_id=handoff_id)

    def transition_claimed(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_id: str,
        claimed_by: str,
        status: str,
        updated_at: str | None = None,
        result: str | None = None,
        rejected_reason: str | None = None,
    ) -> Handoff | None:
        """Conditionally transition a CLAIMED handoff owned by ``claimed_by``.

        Mirrors :meth:`claim`: the WHERE clause re-asserts
        ``status='CLAIMED' AND claimed_by=?`` so a stale caller (lease expired,
        different claimant, already terminal) affects 0 rows instead of
        clobbering the row. The terminal outcome (``result`` on complete,
        ``rejected_reason`` on reject - already serialised TEXT) is written in
        the SAME conditional UPDATE that changes the status, so the row and
        its outcome can never disagree. Returns the updated row, or ``None``
        when 0 rows were affected - the caller re-reads to raise the precise
        catalogue error.
        """
        now = updated_at or self._now()
        sets = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status, now]
        if result is not None:
            sets.append("result = ?")
            params.append(result)
        if rejected_reason is not None:
            sets.append("rejected_reason = ?")
            params.append(rejected_reason)
        params.extend([handoff_id, workspace_id, STATUS_CLAIMED, claimed_by])
        try:
            cur = uow.connection.execute(
                f"UPDATE handoffs SET {', '.join(sets)} "
                "WHERE handoff_id = ? AND workspace_id = ? "
                "AND status = ? AND claimed_by = ?",
                tuple(params),
            )
        except sqlite3.Error as exc:
            raise _db_error("transitioning claimed handoff", exc) from exc
        if cur.rowcount == 0:
            return None
        return self.get(uow, workspace_id=workspace_id, handoff_id=handoff_id)

    def transition_verifying(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_id: str,
        status: str,
        updated_at: str | None = None,
        verification_feedback: str | None = None,
        lease_expires_at: str | None = None,
    ) -> Handoff | None:
        """Conditionally transition a VERIFYING handoff (verify verdict).

        Mirrors :meth:`transition_claimed`: the WHERE clause re-asserts
        ``status='VERIFYING'`` so a stale caller (already decided, expired,
        never verifying) affects 0 rows instead of clobbering the row - the
        caller re-reads to raise the precise catalogue error. The verdict
        outcome rides the SAME conditional UPDATE as the status change:

        - destination ``CLAIMED`` (fail): ``verification_feedback`` is always
          (over)written - including back to NULL, so the column reflects the
          LATEST fail only - and ``lease_expires_at`` is renewed, re-arming
          the executor's lease atomically.
        - terminal destination (pass -> COMPLETED): only status/updated_at
          change; the last feedback and claim fields are left untouched.
        """
        now = updated_at or self._now()
        sets = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status, now]
        if status == STATUS_CLAIMED:
            sets.append("verification_feedback = ?")
            params.append(verification_feedback)
            sets.append("lease_expires_at = ?")
            params.append(lease_expires_at)
        params.extend([handoff_id, workspace_id, STATUS_VERIFYING])
        try:
            cur = uow.connection.execute(
                f"UPDATE handoffs SET {', '.join(sets)} "
                "WHERE handoff_id = ? AND workspace_id = ? AND status = ?",
                tuple(params),
            )
        except sqlite3.Error as exc:
            raise _db_error("transitioning verifying handoff", exc) from exc
        if cur.rowcount == 0:
            return None
        return self.get(uow, workspace_id=workspace_id, handoff_id=handoff_id)

    def reject_open(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_id: str,
        updated_at: str | None = None,
        rejected_reason: str | None = None,
    ) -> Handoff | None:
        """Conditionally reject an unclaimed OPEN handoff (direct-target path).

        Same contract as :meth:`transition_claimed`: the WHERE clause
        re-asserts ``status='OPEN'`` and the optional ``rejected_reason``
        (serialised TEXT) rides the same UPDATE; ``None`` on 0 affected rows.
        """
        now = updated_at or self._now()
        sets = ["status = ?", "updated_at = ?"]
        params: list[Any] = [STATUS_REJECTED, now]
        if rejected_reason is not None:
            sets.append("rejected_reason = ?")
            params.append(rejected_reason)
        params.extend([handoff_id, workspace_id, STATUS_OPEN])
        try:
            cur = uow.connection.execute(
                f"UPDATE handoffs SET {', '.join(sets)} "
                "WHERE handoff_id = ? AND workspace_id = ? AND status = ?",
                tuple(params),
            )
        except sqlite3.Error as exc:
            raise _db_error("rejecting open handoff", exc) from exc
        if cur.rowcount == 0:
            return None
        return self.get(uow, workspace_id=workspace_id, handoff_id=handoff_id)

    def read_outcome(
        self, uow: UnitOfWork, *, workspace_id: str, handoff_id: str
    ) -> dict[str, str | None] | None:
        """Return ``{"result", "rejected_reason", "verification_feedback"}``.

        The outcome columns (migrations 008 + 018) are read separately from
        the :class:`Handoff` dataclass so the shared domain model is
        untouched; the values are the serialised TEXT written by
        :meth:`transition_claimed` / :meth:`reject_open` /
        :meth:`transition_verifying` (opaque, returned verbatim - the same
        contract as ``payload``). ``None`` when the handoff does not exist.
        """
        try:
            cur = uow.connection.execute(
                "SELECT result, rejected_reason, verification_feedback "
                "FROM handoffs WHERE workspace_id = ? AND handoff_id = ?",
                (workspace_id, handoff_id),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading handoff outcome", exc) from exc
        if row is None:
            return None
        return {
            "result": row["result"],
            "rejected_reason": row["rejected_reason"],
            "verification_feedback": row["verification_feedback"],
        }

    def read_verification(
        self, uow: UnitOfWork, *, workspace_id: str, handoff_id: str
    ) -> dict[str, str | None] | None:
        """Return ``{"acceptance_criteria", "verify_by"}``, or ``None``.

        The verification contract columns (migration 018) live outside the
        :class:`Handoff` dataclass (decision D6); both values are the
        serialised TEXT persisted at creation - NULL means the handoff is not
        verifiable (pre-018 row or criteria never requested).
        """
        try:
            cur = uow.connection.execute(
                "SELECT acceptance_criteria, verify_by FROM handoffs "
                "WHERE workspace_id = ? AND handoff_id = ?",
                (workspace_id, handoff_id),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading handoff verification contract", exc) from exc
        if row is None:
            return None
        return {
            "acceptance_criteria": row["acceptance_criteria"],
            "verify_by": row["verify_by"],
        }

    # ----------------------------------------------------------------- #
    # Dependencies (I5, migration 019)
    # ----------------------------------------------------------------- #
    def create_dependencies(
        self,
        uow: UnitOfWork,
        *,
        handoff_id: str,
        workspace_id: str,
        depends_on: list[str],
        created_at: str | None = None,
    ) -> None:
        """Persist the dependent's edges in ITS create transaction (batch).

        One row per dependency, in the caller's (already validated) list
        order - insertion order is the read order. The rows are IMMUTABLE:
        no update/delete path exists on this repo by design.
        """
        now = created_at or self._now()
        try:
            uow.connection.executemany(
                """
                INSERT INTO handoff_dependencies
                    (handoff_id, depends_on_id, workspace_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [(handoff_id, dep_id, workspace_id, now) for dep_id in depends_on],
            )
        except sqlite3.Error as exc:
            raise _db_error("creating handoff dependencies", exc) from exc

    def read_dependencies(
        self, uow: UnitOfWork, *, workspace_id: str, handoff_id: str
    ) -> list[dict[str, Any]]:
        """Return ``[{"depends_on_id", "status"}]`` in creation order.

        ``status`` is the dependency's CURRENT handoff status (the on-read
        derivation - nothing materialised); ``None`` when the dependency row
        has vanished (e.g. admin prune), which callers treat as pending.
        Empty list = the handoff has no dependencies.
        """
        try:
            rows = uow.connection.execute(
                "SELECT d.depends_on_id, h.status "
                "FROM handoff_dependencies d "
                "LEFT JOIN handoffs h ON h.handoff_id = d.depends_on_id "
                "AND h.workspace_id = d.workspace_id "
                "WHERE d.workspace_id = ? AND d.handoff_id = ? "
                "ORDER BY d.rowid",
                (workspace_id, handoff_id),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("reading handoff dependencies", exc) from exc
        return [
            {"depends_on_id": row["depends_on_id"], "status": row["status"]}
            for row in rows
        ]

    def dependents_of(
        self, uow: UnitOfWork, *, workspace_id: str, depends_on_id: str
    ) -> list[str]:
        """Return the handoff_ids that depend on ``depends_on_id``.

        The reverse-index lookup (idx_handoff_deps_reverse) used by the
        synchronous unblock / dependency-failed paths right after a
        dependency reaches a terminal status. Creation order.
        """
        try:
            rows = uow.connection.execute(
                "SELECT handoff_id FROM handoff_dependencies "
                "WHERE workspace_id = ? AND depends_on_id = ? "
                "ORDER BY rowid",
                (workspace_id, depends_on_id),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("resolving handoff dependents", exc) from exc
        return [row["handoff_id"] for row in rows]

    def dependency_aggregates(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_ids: Iterable[str],
    ) -> dict[str, dict[str, Any]]:
        """Per-handoff aggregates for a page of ids (one ``IN`` query).

        Delegates to the module-level :func:`dependency_aggregates_for` (the
        single shared implementation); see its docstring for the shape.
        """
        return dependency_aggregates_for(
            uow, workspace_id=workspace_id, handoff_ids=handoff_ids
        )

    def update_status(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_id: str,
        status: str,
        updated_at: str | None = None,
    ) -> Handoff:
        """Unconditional status write (port method).

        Lifecycle transitions (complete/reject) must NOT use this - they go
        through :meth:`transition_claimed` / :meth:`reject_open` so the state
        precondition is re-asserted in the UPDATE itself.
        """
        now = updated_at or self._now()
        try:
            cur = uow.connection.execute(
                "UPDATE handoffs SET status = ?, updated_at = ? "
                "WHERE handoff_id = ? AND workspace_id = ?",
                (status, now, handoff_id, workspace_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("updating handoff status", exc) from exc
        if cur.rowcount == 0:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "handoff_id does not exist in this workspace.",
                {"handoff_id": handoff_id, "workspace_id": workspace_id},
            )
        row = self.get(uow, workspace_id=workspace_id, handoff_id=handoff_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "handoff_id does not exist in this workspace.",
                {"handoff_id": handoff_id},
            )
        return row

    def list(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        status: str | None = None,
        target: str | None = None,
    ) -> list[Handoff]:
        sql = f"SELECT {self._COLUMNS} FROM handoffs WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        if target is not None:
            sql += " AND target = ?"
            params.append(target)
        sql += " ORDER BY created_at, handoff_id"
        try:
            cur = uow.connection.execute(sql, tuple(params))
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing handoffs", exc) from exc
        return [self._row_to_handoff(row) for row in rows]

    @staticmethod
    def _row_to_handoff(row: Any) -> Handoff:
        return Handoff(
            handoff_id=row["handoff_id"],
            workspace_id=row["workspace_id"],
            status=row["status"],
            created_at=row["created_at"],
            task_id=row["task_id"],
            from_agent_id=row["from_agent_id"],
            target=row["target"],
            visibility=row["visibility"],
            claimed_by=row["claimed_by"],
            lease_expires_at=row["lease_expires_at"],
            updated_at=row["updated_at"],
            payload=row["payload"],
            trace_id=row["trace_id"],
        )
