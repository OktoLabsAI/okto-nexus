"""SQLite repositories for the identity slice.

Concrete implementations of :class:`WorkspaceRepo`, :class:`AgentRepo`, and
:class:`SessionRepo` (from :mod:`okto_nexus.application.ports`). Every method
operates on ``uow.connection`` inside the caller's active transaction, so state
mutations and audit events commit atomically.

This is an outbound adapter, so it is allowed to import ``sqlite3`` and the
domain dataclasses. JSON-ish columns (``capabilities``/``metadata``) are
(de)serialised here. Timestamps default to the injected clock (falling back to
:func:`utc_now_iso`) when the caller does not supply one.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.models import Agent, Session, Workspace
from ....errors import ErrorCode, OktoNexusError


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _loads(text: str | None) -> Any:
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _db_error(action: str, exc: sqlite3.Error) -> OktoNexusError:
    return OktoNexusError(
        ErrorCode.DB_ERROR,
        f"SQLite failure while {action}.",
        {"reason": str(exc)},
    )


class _ClockBacked:
    """Mixin providing a ``_now`` timestamp from an optional injected clock."""

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock.now_iso()
        return utc_now_iso()


class SqliteWorkspaceRepo(_ClockBacked):
    """Persistence for ``workspaces`` rows (keyed by ``workspace_id``)."""

    def upsert(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        display_name: str | None = None,
        root_realpath: str | None = None,
        last_seen_at: str | None = None,
    ) -> Workspace:
        now = last_seen_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO workspaces
                    (workspace_id, display_name, root_realpath, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    display_name = COALESCE(excluded.display_name, workspaces.display_name),
                    root_realpath = COALESCE(excluded.root_realpath, workspaces.root_realpath),
                    last_seen_at = excluded.last_seen_at
                """,
                (workspace_id, display_name, root_realpath, now, now),
            )
        except sqlite3.Error as exc:
            raise _db_error("upserting workspace", exc) from exc
        row = self.get(uow, workspace_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Workspace missing immediately after upsert.",
                {"workspace_id": workspace_id},
            )
        return row

    def get(self, uow: UnitOfWork, workspace_id: str) -> Workspace | None:
        try:
            cur = uow.connection.execute(
                """
                SELECT workspace_id, display_name, root_realpath, created_at, last_seen_at
                FROM workspaces WHERE workspace_id = ?
                """,
                (workspace_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading workspace", exc) from exc
        if row is None:
            return None
        return self._row_to_workspace(row)

    def list_all(self, uow: UnitOfWork) -> list[Workspace]:
        """Return every workspace (global-admin; NOT workspace-scoped)."""
        try:
            cur = uow.connection.execute(
                """
                SELECT workspace_id, display_name, root_realpath, created_at, last_seen_at
                FROM workspaces ORDER BY created_at, workspace_id
                """
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing workspaces", exc) from exc
        return [self._row_to_workspace(row) for row in rows]

    @staticmethod
    def _row_to_workspace(row: Any) -> Workspace:
        return Workspace(
            workspace_id=row["workspace_id"],
            created_at=row["created_at"],
            display_name=row["display_name"],
            root_realpath=row["root_realpath"],
            last_seen_at=row["last_seen_at"],
        )


class SqliteAgentRepo(_ClockBacked):
    """Persistence for ``agents`` rows (global logical identities)."""

    _COLUMNS = "agent_id, role, capabilities, metadata, created_at, last_seen_at"

    def upsert(
        self,
        uow: UnitOfWork,
        *,
        agent_id: str,
        role: str | None = None,
        capabilities: Any = None,
        metadata: Any = None,
    ) -> Agent:
        now = self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO agents (agent_id, role, capabilities, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    role = COALESCE(excluded.role, agents.role),
                    capabilities = COALESCE(excluded.capabilities, agents.capabilities),
                    metadata = COALESCE(excluded.metadata, agents.metadata)
                """,
                (agent_id, role, _dumps(capabilities), _dumps(metadata), now),
            )
        except sqlite3.Error as exc:
            raise _db_error("upserting agent", exc) from exc
        row = self.get(uow, agent_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Agent missing immediately after upsert.",
                {"agent_id": agent_id},
            )
        return row

    def get(self, uow: UnitOfWork, agent_id: str) -> Agent | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM agents WHERE agent_id = ?",
                (agent_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading agent", exc) from exc
        if row is None:
            return None
        return self._row_to_agent(row)

    def list(self, uow: UnitOfWork) -> list[Agent]:
        """Return ALL agents (global; not workspace-scoped), oldest first."""
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM agents ORDER BY created_at, agent_id"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing agents", exc) from exc
        return [self._row_to_agent(row) for row in rows]

    def touch(
        self, uow: UnitOfWork, *, agent_id: str, at: str | None = None
    ) -> bool:
        """Stamp ``last_seen_at`` for an agent; no-op (False) if it is absent."""
        now = at or self._now()
        try:
            cur = uow.connection.execute(
                "UPDATE agents SET last_seen_at = ? WHERE agent_id = ?",
                (now, agent_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("touching agent", exc) from exc
        return cur.rowcount > 0

    @staticmethod
    def _row_to_agent(row: Any) -> Agent:
        capabilities = _loads(row["capabilities"])
        metadata = _loads(row["metadata"])
        return Agent(
            agent_id=row["agent_id"],
            created_at=row["created_at"],
            role=row["role"],
            capabilities=capabilities if capabilities is not None else {},
            metadata=metadata if metadata is not None else {},
            last_seen_at=row["last_seen_at"],
        )


class SqliteSessionRepo(_ClockBacked):
    """Persistence for ``sessions`` rows (workspace-scoped)."""

    _COLUMNS = (
        "session_id, agent_id, workspace_id, status, started_at, "
        "last_heartbeat_at, closed_at"
    )

    def create(
        self,
        uow: UnitOfWork,
        *,
        session_id: str,
        agent_id: str,
        workspace_id: str,
        status: str,
        started_at: str | None = None,
    ) -> Session:
        now = started_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO sessions
                    (session_id, agent_id, workspace_id, status, started_at, last_heartbeat_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, agent_id, workspace_id, status, now, now),
            )
        except sqlite3.Error as exc:
            raise _db_error("creating session", exc) from exc
        row = self.get(uow, session_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Session missing immediately after insert.",
                {"session_id": session_id},
            )
        return row

    def get(self, uow: UnitOfWork, session_id: str) -> Session | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading session", exc) from exc
        if row is None:
            return None
        return self._row_to_session(row)

    def heartbeat(
        self, uow: UnitOfWork, *, session_id: str, at: str | None = None
    ) -> Session:
        now = at or self._now()
        try:
            cur = uow.connection.execute(
                "UPDATE sessions SET last_heartbeat_at = ? WHERE session_id = ?",
                (now, session_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("updating session heartbeat", exc) from exc
        if cur.rowcount == 0:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "session_id does not exist.",
                {"session_id": session_id},
            )
        row = self.get(uow, session_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "session_id does not exist.",
                {"session_id": session_id},
            )
        return row

    def close(
        self, uow: UnitOfWork, *, session_id: str, at: str | None = None
    ) -> Session:
        now = at or self._now()
        try:
            # Idempotent: only the FIRST close stamps status/closed_at; a repeat
            # matches zero rows (status already 'closed') yet the row persists,
            # so the existence check below uses get(), never rowcount.
            uow.connection.execute(
                """
                UPDATE sessions
                SET status = 'closed', closed_at = ?
                WHERE session_id = ? AND status != 'closed'
                """,
                (now, session_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("closing session", exc) from exc
        row = self.get(uow, session_id)
        if row is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "session_id does not exist.",
                {"session_id": session_id},
            )
        return row

    def list(
        self, uow: UnitOfWork, *, workspace_id: str, status: str | None = None
    ) -> list[Session]:
        sql = f"SELECT {self._COLUMNS} FROM sessions WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY started_at, session_id"
        try:
            cur = uow.connection.execute(sql, tuple(params))
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing sessions", exc) from exc
        return [self._row_to_session(row) for row in rows]

    @staticmethod
    def _row_to_session(row: Any) -> Session:
        return Session(
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            workspace_id=row["workspace_id"],
            status=row["status"],
            started_at=row["started_at"],
            last_heartbeat_at=row["last_heartbeat_at"],
            closed_at=row["closed_at"],
        )
