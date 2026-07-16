"""SQLite repository for HITL approvals (migration 017, spec 2948b2a2).

Concrete :class:`okto_nexus.application.ports.ApprovalRepo` over ``approvals``.
Rows are append-then-decide, never deleted (BR1). ``mark_decided`` is the
CONDITIONAL pending-only UPDATE backing the anti-double-decision guarantee
(AC6); ``revert_to_pending`` is the honest rollback after a failed
re-execution gate (BR3). Payload columns stay JSON TEXT - (de)serialisation
belongs to the application service.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from ....application.ports import UnitOfWork
from ....domain.approvals import STATUS_PENDING, Approval
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


class SqliteApprovalRepo:
    """Persistence for the ``approvals`` table."""

    _COLUMNS = (
        "approval_id, workspace_id, agent_id, action, policy_id, "
        "request_payload, status, decided_by, justification, executed_result, "
        "trace_id, created_at, decided_at"
    )

    def add(
        self,
        uow: UnitOfWork,
        *,
        approval_id: str,
        workspace_id: str,
        agent_id: str,
        action: str,
        policy_id: str,
        request_payload: str,
        trace_id: str | None,
        created_at: str,
    ) -> Approval:
        try:
            uow.connection.execute(
                """
                INSERT INTO approvals
                    (approval_id, workspace_id, agent_id, action, policy_id,
                     request_payload, status, trace_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    workspace_id,
                    agent_id,
                    action,
                    policy_id,
                    request_payload,
                    STATUS_PENDING,
                    trace_id,
                    created_at,
                ),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("creating approval", exc) from exc
        row = self.get(uow, approval_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Approval missing immediately after insert.",
                {"approval_id": approval_id},
            )
        return row

    def get(self, uow: UnitOfWork, approval_id: str) -> Approval | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM approvals WHERE approval_id = ?",
                (approval_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading approval", exc) from exc
        return None if row is None else self._row_to_approval(row)

    def list(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Approval]:
        """Workspace-scoped, ASCENDING created_at (the oldest-first queue)."""
        sql = f"SELECT {self._COLUMNS} FROM approvals WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at, approval_id LIMIT ?"
        params.append(int(limit))
        try:
            rows = uow.connection.execute(sql, tuple(params)).fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing approvals", exc) from exc
        return [self._row_to_approval(row) for row in rows]

    def mark_decided(
        self,
        uow: UnitOfWork,
        *,
        approval_id: str,
        status: str,
        decided_by: str,
        justification: str | None,
        decided_at: str,
    ) -> bool:
        """Pending-only conditional flip; ``False`` = already decided (AC6)."""
        try:
            cur = uow.connection.execute(
                """
                UPDATE approvals
                   SET status = ?, decided_by = ?, justification = ?,
                       decided_at = ?
                 WHERE approval_id = ? AND status = ?
                """,
                (
                    status,
                    decided_by,
                    justification,
                    decided_at,
                    approval_id,
                    STATUS_PENDING,
                ),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("deciding approval", exc) from exc
        return cur.rowcount > 0

    def set_executed_result(
        self, uow: UnitOfWork, *, approval_id: str, executed_result: str
    ) -> None:
        try:
            uow.connection.execute(
                "UPDATE approvals SET executed_result = ? WHERE approval_id = ?",
                (executed_result, approval_id),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("recording approval result", exc) from exc

    def revert_to_pending(self, uow: UnitOfWork, *, approval_id: str) -> None:
        """Honest rollback (BR3): clear the decision, keep the row auditable."""
        try:
            uow.connection.execute(
                """
                UPDATE approvals
                   SET status = ?, decided_by = NULL, justification = NULL,
                       decided_at = NULL
                 WHERE approval_id = ?
                """,
                (STATUS_PENDING, approval_id),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("reverting approval", exc) from exc

    @staticmethod
    def _row_to_approval(row: Any) -> Approval:
        return Approval(
            approval_id=row["approval_id"],
            workspace_id=row["workspace_id"],
            agent_id=row["agent_id"],
            action=row["action"],
            policy_id=row["policy_id"],
            request_payload=row["request_payload"],
            status=row["status"],
            decided_by=row["decided_by"],
            justification=row["justification"],
            executed_result=row["executed_result"],
            trace_id=row["trace_id"],
            created_at=row["created_at"],
            decided_at=row["decided_at"],
        )
