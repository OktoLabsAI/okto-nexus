"""SQLite repository for ephemeral poll tokens."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.models import EphemeralPollToken
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


def _dumps(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, separators=(",", ":"))


def _loads(text: str | None) -> dict[str, Any]:
    if text is None:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _db_error(action: str, exc: sqlite3.Error) -> OktoNexusError:
    return db_error_from_exception(action, exc)


class SqlitePollTokenRepo:
    """Persistence for short-lived monitor bearer tokens."""

    _COLUMNS = (
        "token_id, token_hash, agent_id, workspace_id, session_id, "
        "issue_cursor, scope, expires_at, revoked_at, created_at, renewed_at, "
        "last_used_at"
    )

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock.now_iso()
        return utc_now_iso()

    def issue(
        self,
        uow: UnitOfWork,
        *,
        token_id: str,
        token_hash: str,
        agent_id: str,
        workspace_id: str,
        session_id: str,
        issue_cursor: int,
        scope: Mapping[str, Any],
        expires_at: str,
        created_at: str,
    ) -> EphemeralPollToken:
        """Revoke any active token for this agent/workspace, then insert."""
        try:
            uow.connection.execute(
                """
                UPDATE ephemeral_poll_tokens
                SET revoked_at = ?
                WHERE agent_id = ? AND workspace_id = ? AND revoked_at IS NULL
                """,
                (created_at, agent_id, workspace_id),
            )
            uow.connection.execute(
                """
                INSERT INTO ephemeral_poll_tokens
                    (token_id, token_hash, agent_id, workspace_id, session_id,
                     issue_cursor, scope, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_id,
                    token_hash,
                    agent_id,
                    workspace_id,
                    session_id,
                    int(issue_cursor),
                    _dumps(scope),
                    expires_at,
                    created_at,
                ),
            )
        except sqlite3.Error as exc:
            raise _db_error("issuing poll token", exc) from exc
        row = self.get_by_hash(uow, token_hash=token_hash)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Poll token missing immediately after insert.",
                {"token_id": token_id},
            )
        return row

    def get_active_for_session(
        self, uow: UnitOfWork, *, session_id: str
    ) -> EphemeralPollToken | None:
        try:
            row = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM ephemeral_poll_tokens "
                "WHERE session_id = ? AND revoked_at IS NULL "
                "ORDER BY created_at DESC, token_id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading active poll token", exc) from exc
        return self._row(row) if row is not None else None

    def get_by_hash(
        self, uow: UnitOfWork, *, token_hash: str
    ) -> EphemeralPollToken | None:
        try:
            row = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM ephemeral_poll_tokens "
                "WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading poll token by hash", exc) from exc
        return self._row(row) if row is not None else None

    def rotate(
        self,
        uow: UnitOfWork,
        *,
        token_id: str,
        token_hash: str,
        expires_at: str,
        renewed_at: str,
    ) -> EphemeralPollToken:
        try:
            cur = uow.connection.execute(
                """
                UPDATE ephemeral_poll_tokens
                SET token_hash = ?, expires_at = ?, renewed_at = ?,
                    revoked_at = NULL
                WHERE token_id = ? AND revoked_at IS NULL
                """,
                (token_hash, expires_at, renewed_at, token_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("rotating poll token", exc) from exc
        if cur.rowcount == 0:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "No active poll token exists for this session.",
                {"token_id": token_id},
            )
        row = self.get_by_hash(uow, token_hash=token_hash)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Poll token missing immediately after rotation.",
                {"token_id": token_id},
            )
        return row

    def revoke_for_session(
        self, uow: UnitOfWork, *, session_id: str, revoked_at: str
    ) -> int:
        try:
            cur = uow.connection.execute(
                """
                UPDATE ephemeral_poll_tokens
                SET revoked_at = ?
                WHERE session_id = ? AND revoked_at IS NULL
                """,
                (revoked_at, session_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("revoking poll token", exc) from exc
        return int(cur.rowcount)

    def touch_used(self, uow: UnitOfWork, *, token_id: str, at: str) -> bool:
        try:
            cur = uow.connection.execute(
                "UPDATE ephemeral_poll_tokens SET last_used_at = ? WHERE token_id = ?",
                (at, token_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("touching poll token", exc) from exc
        return cur.rowcount > 0

    @staticmethod
    def _row(row: Any) -> EphemeralPollToken:
        return EphemeralPollToken(
            token_id=row["token_id"],
            token_hash=row["token_hash"],
            agent_id=row["agent_id"],
            workspace_id=row["workspace_id"],
            session_id=row["session_id"],
            issue_cursor=int(row["issue_cursor"]),
            scope=_loads(row["scope"]),
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
            created_at=row["created_at"],
            renewed_at=row["renewed_at"],
            last_used_at=row["last_used_at"],
        )
