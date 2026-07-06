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
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


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

    _COLUMNS = (
        "agent_id, role, capabilities, metadata, created_at, last_seen_at, "
        "api_key_hash, is_active, permissions, preset_id, tags, comm_scope, color"
    )

    def upsert(
        self,
        uow: UnitOfWork,
        *,
        agent_id: str,
        role: str | None = None,
        capabilities: Any = None,
        metadata: Any = None,
        color: str | None = None,
    ) -> Agent:
        now = self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO agents (agent_id, role, capabilities, metadata, created_at, color)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    role = COALESCE(excluded.role, agents.role),
                    capabilities = COALESCE(excluded.capabilities, agents.capabilities),
                    metadata = COALESCE(excluded.metadata, agents.metadata),
                    color = COALESCE(excluded.color, agents.color)
                """,
                (agent_id, role, _dumps(capabilities), _dumps(metadata), now, color),
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

    def touch(self, uow: UnitOfWork, *, agent_id: str, at: str | None = None) -> bool:
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

    def set_permissions(
        self,
        uow: UnitOfWork,
        *,
        agent_id: str,
        permissions: Any,
        preset_id: str | None,
    ) -> bool:
        """Overwrite BOTH permission columns; True if the agent existed.

        Always a full overwrite (``None`` resets to unrestricted) - unlike
        ``upsert``'s COALESCE semantics, clearing is a first-class operation
        here, so a dedicated method keeps the intent unambiguous.
        """
        try:
            cur = uow.connection.execute(
                "UPDATE agents SET permissions = ?, preset_id = ? WHERE agent_id = ?",
                (_dumps(permissions), preset_id, agent_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("setting agent permissions", exc) from exc
        return cur.rowcount > 0

    def set_tags(self, uow: UnitOfWork, *, agent_id: str, tags: Any) -> bool:
        """Overwrite the agent's ``tags`` column; True if the agent existed.

        Always a full overwrite (``None`` resets to "no tags") - mirroring
        :meth:`set_permissions`, clearing is a first-class operation here.
        Catalog existence is the APPLICATION layer's job; this method persists
        an already-validated value verbatim.
        """
        try:
            cur = uow.connection.execute(
                "UPDATE agents SET tags = ? WHERE agent_id = ?",
                (_dumps(tags), agent_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("setting agent tags", exc) from exc
        return cur.rowcount > 0

    def set_comm_scope(
        self, uow: UnitOfWork, *, agent_id: str, comm_scope: Any
    ) -> bool:
        """Overwrite the agent's ``comm_scope``; True if the agent existed.

        Full overwrite (``None`` resets to unrestricted). The value is the
        operator-set communication scope and is PRIVATE - read surfaces must
        never expose it on discovery.
        """
        try:
            cur = uow.connection.execute(
                "UPDATE agents SET comm_scope = ? WHERE agent_id = ?",
                (_dumps(comm_scope), agent_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("setting agent comm_scope", exc) from exc
        return cur.rowcount > 0

    def set_color(self, uow: UnitOfWork, *, agent_id: str, color: str | None) -> bool:
        """Overwrite the agent's ``color`` column; True if the agent existed.

        Full overwrite (``None`` resets to auto-by-identity) - mirroring
        :meth:`set_tags`, clearing is a first-class operation here. The value
        is a plain string (e.g. "#22c55e") stored verbatim; format validation
        is the caller's job.
        """
        try:
            cur = uow.connection.execute(
                "UPDATE agents SET color = ? WHERE agent_id = ?",
                (color, agent_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("setting agent color", exc) from exc
        return cur.rowcount > 0

    def get_active_by_key_hash(
        self, uow: UnitOfWork, *, api_key_hash: str
    ) -> Agent | None:
        """Resolve an ACTIVE agent by key hash (migration 009, D5).

        ``None`` covers both an unknown hash and an inactive agent: the auth
        failure must be uniform so a revoked key is indistinguishable from a
        bogus one. The partial UNIQUE index guarantees at most one row.
        """
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM agents "
                "WHERE api_key_hash = ? AND is_active = 1",
                (api_key_hash,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("resolving agent by key hash", exc) from exc
        if row is None:
            return None
        return self._row_to_agent(row)

    def set_key_hash(
        self, uow: UnitOfWork, *, agent_id: str, api_key_hash: str | None
    ) -> bool:
        """Set (or clear) the agent's key hash; True if the agent existed.

        Replacing the hash IS the regeneration primitive: the previous key
        stops resolving within this transaction (immediate invalidation).
        A duplicate hash violates the partial UNIQUE index and surfaces as
        a DB_ERROR (callers generate fresh random keys, so a collision is
        a bug or an attempted reuse - never silently accepted).
        """
        try:
            cur = uow.connection.execute(
                "UPDATE agents SET api_key_hash = ? WHERE agent_id = ?",
                (api_key_hash, agent_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("setting agent key hash", exc) from exc
        return cur.rowcount > 0

    def set_active(self, uow: UnitOfWork, *, agent_id: str, is_active: bool) -> bool:
        """Flip the revocation switch; True if the agent existed."""
        try:
            cur = uow.connection.execute(
                "UPDATE agents SET is_active = ? WHERE agent_id = ?",
                (1 if is_active else 0, agent_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("setting agent active flag", exc) from exc
        return cur.rowcount > 0

    def list_without_key(self, uow: UnitOfWork) -> list[Agent]:
        """Agents with no issued key, oldest first (`admin issue-keys` view)."""
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM agents "
                "WHERE api_key_hash IS NULL ORDER BY created_at, agent_id"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing agents without key", exc) from exc
        return [self._row_to_agent(row) for row in rows]

    def delete(self, uow: UnitOfWork, *, agent_id: str) -> bool:
        """Remove the agent and its OWN dependent rows; True if it existed.

        ``agents(agent_id)`` is referenced by ``sessions.agent_id`` and
        ``message_deliveries.recipient_agent_id`` (both NOT NULL FKs), so a
        bare DELETE on a real, active identity fails the constraint
        (DB_ERROR). The management-surface contract is an IRREVERSIBLE
        cleanup, so we cascade in FK-safe order inside the caller's
        transaction: drop the agent's inbox deliveries (as recipient) and its
        sessions first, then the identity. Messages it SENT are preserved -
        ``messages.from_agent_id`` is not an FK, and other agents' inboxes
        still reference those rows; erasing them would orphan peers'
        deliveries. (Whole-store history removal is the reset surface, not
        this.)
        """
        try:
            uow.connection.execute(
                "DELETE FROM message_deliveries WHERE recipient_agent_id = ?",
                (agent_id,),
            )
            uow.connection.execute(
                "DELETE FROM sessions WHERE agent_id = ?", (agent_id,)
            )
            cur = uow.connection.execute(
                "DELETE FROM agents WHERE agent_id = ?", (agent_id,)
            )
        except sqlite3.Error as exc:
            raise _db_error("deleting agent", exc) from exc
        return cur.rowcount > 0

    @staticmethod
    def _row_to_agent(row: Any) -> Agent:
        capabilities = _loads(row["capabilities"])
        metadata = _loads(row["metadata"])
        tags = _loads(row["tags"])
        return Agent(
            agent_id=row["agent_id"],
            created_at=row["created_at"],
            role=row["role"],
            capabilities=capabilities if capabilities is not None else {},
            metadata=metadata if metadata is not None else {},
            last_seen_at=row["last_seen_at"],
            api_key_hash=row["api_key_hash"],
            is_active=bool(row["is_active"]),
            permissions=_loads(row["permissions"]),
            preset_id=row["preset_id"],
            tags=tags if tags is not None else {},
            comm_scope=_loads(row["comm_scope"]),
            color=row["color"],
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
        session_secret: str | None = None,
    ) -> Session:
        now = started_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO sessions
                    (session_id, agent_id, workspace_id, status, started_at,
                     last_heartbeat_at, session_secret)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, agent_id, workspace_id, status, now, now, session_secret),
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

    def get_secret(self, uow: UnitOfWork, *, session_id: str) -> str | None:
        """Return the stored ``session_secret`` for a session (or ``None``).

        ``None`` both for an unknown session and for a session opened before
        migration 007 (NULL column) - callers that need to distinguish the two
        check existence via :meth:`get` first. The secret is deliberately NOT
        part of the :class:`Session` dataclass, so no list/read surface can
        ever leak it.
        """
        try:
            cur = uow.connection.execute(
                "SELECT session_secret FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading session secret", exc) from exc
        return None if row is None else row["session_secret"]

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

    def count_closed_before(self, uow: UnitOfWork, *, cutoff: str) -> int:
        """Count ``closed`` sessions that were closed before ``cutoff``.

        The prune dry-run view: matches EXACTLY the predicate of
        :meth:`prune_closed_before` (``COALESCE`` falls back to the heartbeat /
        start stamps for a closed row missing ``closed_at``, e.g. pre-002).
        """
        try:
            row = uow.connection.execute(
                "SELECT COUNT(*) FROM sessions WHERE status = 'closed' "
                "AND COALESCE(closed_at, last_heartbeat_at, started_at) < ?",
                (cutoff,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise _db_error("counting prunable sessions", exc) from exc
        return int(row[0])

    def prune_closed_before(self, uow: UnitOfWork, *, cutoff: str, limit: int) -> int:
        """Delete up to ``limit`` ``closed`` sessions closed before ``cutoff``.

        The ONLY delete path on ``sessions``, used exclusively by the retention
        slice. The ``status = 'closed'`` predicate is baked into the SQL, so
        live state is unreachable BY CONSTRUCTION: ``active``/``stale``
        sessions are never deleted regardless of age (the session reaper closes
        them first; only then do they age into this window). Bounded by
        ``limit`` per batch so the WAL writer lock is held briefly.
        """
        try:
            cur = uow.connection.execute(
                """
                DELETE FROM sessions WHERE session_id IN (
                    SELECT session_id FROM sessions
                    WHERE status = 'closed'
                      AND COALESCE(closed_at, last_heartbeat_at, started_at) < ?
                    ORDER BY COALESCE(closed_at, last_heartbeat_at, started_at) ASC,
                             session_id ASC
                    LIMIT ?
                )
                """,
                (cutoff, int(limit)),
            )
        except sqlite3.Error as exc:
            raise _db_error("pruning closed sessions", exc) from exc
        return int(cur.rowcount)

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
