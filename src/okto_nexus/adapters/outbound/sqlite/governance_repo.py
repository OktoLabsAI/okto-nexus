"""SQLite repository for governance policies (migration 016).

Concrete :class:`okto_nexus.application.ports.GovernanceRepo` implementation
over ``governance_policies``, plus the on-demand consumption counters the
enforcement point pre-fetches INSIDE the write path's own unit of work (spec
ffef15bf: sliding windows are always derived from the existing tables - never a
counter table). Policies are GLOBAL (no workspace_id) in V1.

The stored column is ``time_window`` (clear of the SQLite ``WINDOW`` keyword);
the domain/contract field is ``window`` - this repo owns the mapping. Form
validation is upstream (``domain.governance.validate_policy_form``); this repo
persists.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.governance import (
    ACTION_ARTIFACT_PUT,
    ACTION_BROADCAST,
    ACTION_HANDOFF_CREATE,
    ACTION_MESSAGE_CREATE,
    Policy,
)
from ....domain.handoff import TERMINAL_STATUSES
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception

#: Which table backs the max_count window of each action (BR3): message counts
#: cover message_create AND broadcast (both are rows in ``messages``).
_COUNT_SQL: dict[str, str] = {
    ACTION_MESSAGE_CREATE: (
        "SELECT COUNT(*) FROM messages WHERE from_agent_id = ? AND created_at >= ?"
    ),
    ACTION_BROADCAST: (
        "SELECT COUNT(*) FROM messages WHERE from_agent_id = ? AND created_at >= ?"
    ),
    ACTION_HANDOFF_CREATE: (
        "SELECT COUNT(*) FROM handoffs WHERE from_agent_id = ? AND created_at >= ?"
    ),
    ACTION_ARTIFACT_PUT: (
        "SELECT COUNT(*) FROM artifacts WHERE created_by = ? AND created_at >= ?"
    ),
}

_MUTABLE_FIELDS = (
    "subject_kind",
    "subject_value",
    "action",
    "limit_kind",
    "limit_value",
    "window",
    "enabled",
)


class SqliteGovernanceRepo:
    """Persistence + consumption counters for ``governance_policies``."""

    _COLUMNS = (
        "policy_id, subject_kind, subject_value, action, limit_kind, "
        "limit_value, time_window, enabled, created_at, updated_at"
    )

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        return self._clock.now_iso() if self._clock is not None else utc_now_iso()

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #
    def create(
        self,
        uow: UnitOfWork,
        *,
        policy_id: str,
        subject_kind: str,
        subject_value: str | None,
        action: str,
        limit_kind: str,
        limit_value: int | None,
        window: str | None,
        enabled: bool = True,
        created_at: str | None = None,
    ) -> Policy:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO governance_policies
                    (policy_id, subject_kind, subject_value, action, limit_kind,
                     limit_value, time_window, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    policy_id,
                    subject_kind,
                    subject_value,
                    action,
                    limit_kind,
                    limit_value,
                    window,
                    1 if enabled else 0,
                    now,
                    now,
                ),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("creating governance policy", exc) from exc
        row = self.get(uow, policy_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Governance policy missing immediately after insert.",
                {"policy_id": policy_id},
            )
        return row

    def get(self, uow: UnitOfWork, policy_id: str) -> Policy | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM governance_policies WHERE policy_id = ?",
                (policy_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading governance policy", exc) from exc
        return None if row is None else self._row_to_policy(row)

    def list(self, uow: UnitOfWork) -> list[Policy]:
        """Every policy (enabled AND disabled), in deterministic order."""
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM governance_policies "
                "ORDER BY created_at, policy_id"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing governance policies", exc) from exc
        return [self._row_to_policy(row) for row in rows]

    def list_active(self, uow: UnitOfWork) -> list[Policy]:
        """Enabled policies only - the enforcement read."""
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM governance_policies "
                "WHERE enabled = 1 ORDER BY created_at, policy_id"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing governance policies", exc) from exc
        return [self._row_to_policy(row) for row in rows]

    def update(
        self, uow: UnitOfWork, *, policy_id: str, fields: Mapping[str, Any]
    ) -> Policy | None:
        """Patch ``fields`` (already validated upstream); None when absent."""
        sets: list[str] = []
        params: list[Any] = []
        for name in _MUTABLE_FIELDS:
            if name not in fields:
                continue
            value = fields[name]
            if name == "window":
                sets.append("time_window = ?")
                params.append(value)
            elif name == "enabled":
                sets.append("enabled = ?")
                params.append(1 if value else 0)
            else:
                sets.append(f"{name} = ?")
                params.append(value)
        if not sets:
            return self.get(uow, policy_id)
        sets.append("updated_at = ?")
        params.append(self._now())
        params.append(policy_id)
        try:
            cur = uow.connection.execute(
                f"UPDATE governance_policies SET {', '.join(sets)} WHERE policy_id = ?",
                tuple(params),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("updating governance policy", exc) from exc
        if cur.rowcount == 0:
            return None
        return self.get(uow, policy_id)

    def delete(self, uow: UnitOfWork, *, policy_id: str) -> bool:
        try:
            cur = uow.connection.execute(
                "DELETE FROM governance_policies WHERE policy_id = ?", (policy_id,)
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("deleting governance policy", exc) from exc
        return cur.rowcount > 0

    # ------------------------------------------------------------------ #
    # Consumption counters (pre-fetched inside the write path's UoW)
    # ------------------------------------------------------------------ #
    def actions_since(
        self, uow: UnitOfWork, *, agent_id: str, action: str, since: str
    ) -> int:
        """COUNT of the caller's persisted ``action`` rows at/after ``since``.

        GLOBAL per agent (no workspace filter - matches the precedent of
        ``messages.count_since``). Canonical fixed-width ISO timestamps make the
        lexicographic ``>=`` chronological.
        """
        sql = _COUNT_SQL.get(action)
        if sql is None:  # pragma: no cover - vocabulary enforced upstream
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"No consumption counter for action {action!r}.",
                {"action": action},
            )
        try:
            row = uow.connection.execute(sql, (agent_id, since)).fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("counting recent actions", exc) from exc
        return int(row[0])

    def open_handoffs(self, uow: UnitOfWork, *, agent_id: str) -> int:
        """COUNT of the caller's handoffs in a NON-terminal status (global)."""
        placeholders = ", ".join("?" for _ in TERMINAL_STATUSES)
        try:
            row = uow.connection.execute(
                "SELECT COUNT(*) FROM handoffs "
                f"WHERE from_agent_id = ? AND status NOT IN ({placeholders})",
                (agent_id, *sorted(TERMINAL_STATUSES)),
            ).fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("counting open handoffs", exc) from exc
        return int(row[0])

    @staticmethod
    def _row_to_policy(row: Any) -> Policy:
        return Policy(
            policy_id=row["policy_id"],
            subject_kind=row["subject_kind"],
            subject_value=row["subject_value"],
            action=row["action"],
            limit_kind=row["limit_kind"],
            limit_value=row["limit_value"],
            window=row["time_window"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
        )
