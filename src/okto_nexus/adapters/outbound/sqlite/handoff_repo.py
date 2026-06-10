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
from typing import Any, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.handoff import STATUS_CLAIMED, STATUS_OPEN, STATUS_REJECTED
from ....domain.models import Handoff, Task
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


def _db_error(action: str, exc: sqlite3.Error) -> OktoNexusError:
    # Centralised classification: lock/busy contention => retryable=True.
    return db_error_from_exception(action, exc)


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
    """Persistence for ``tasks`` rows (workspace-scoped)."""

    _COLUMNS = "task_id, workspace_id, title, description, status, created_by, created_at"

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

    def get(
        self, uow: UnitOfWork, *, workspace_id: str, task_id: str
    ) -> Task | None:
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
        "status, claimed_by, lease_expires_at, created_at, updated_at, payload"
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
        created_at: str | None = None,
    ) -> Handoff:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO handoffs
                    (handoff_id, workspace_id, task_id, from_agent_id, target,
                     visibility, status, claimed_by, lease_expires_at,
                     created_at, updated_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
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
    ) -> Handoff | None:
        """Conditionally transition a CLAIMED handoff owned by ``claimed_by``.

        Mirrors :meth:`claim`: the WHERE clause re-asserts
        ``status='CLAIMED' AND claimed_by=?`` so a stale caller (lease expired,
        different claimant, already terminal) affects 0 rows instead of
        clobbering the row. Returns the updated row, or ``None`` when 0 rows
        were affected - the caller re-reads to raise the precise catalogue
        error.
        """
        now = updated_at or self._now()
        try:
            cur = uow.connection.execute(
                """
                UPDATE handoffs
                   SET status = ?, updated_at = ?
                 WHERE handoff_id = ? AND workspace_id = ?
                   AND status = ? AND claimed_by = ?
                """,
                (status, now, handoff_id, workspace_id, STATUS_CLAIMED, claimed_by),
            )
        except sqlite3.Error as exc:
            raise _db_error("transitioning claimed handoff", exc) from exc
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
    ) -> Handoff | None:
        """Conditionally reject an unclaimed OPEN handoff (direct-target path).

        Same contract as :meth:`transition_claimed`: the WHERE clause
        re-asserts ``status='OPEN'``; ``None`` on 0 affected rows.
        """
        now = updated_at or self._now()
        try:
            cur = uow.connection.execute(
                """
                UPDATE handoffs
                   SET status = ?, updated_at = ?
                 WHERE handoff_id = ? AND workspace_id = ? AND status = ?
                """,
                (STATUS_REJECTED, now, handoff_id, workspace_id, STATUS_OPEN),
            )
        except sqlite3.Error as exc:
            raise _db_error("rejecting open handoff", exc) from exc
        if cur.rowcount == 0:
            return None
        return self.get(uow, workspace_id=workspace_id, handoff_id=handoff_id)

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
        )
