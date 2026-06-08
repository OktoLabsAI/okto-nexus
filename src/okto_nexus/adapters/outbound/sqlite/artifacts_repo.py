"""SQLite repository for the artifacts slice.

Concrete implementation of :class:`okto_nexus.application.ports.ArtifactRepo`.
Every method operates on ``uow.connection`` inside the caller's active
transaction so the metadata row and the ``artifact.created`` event commit
atomically (BR7).

Outbound adapter: it is allowed to import ``sqlite3`` and the domain
dataclasses. Reads are always scoped by ``workspace_id`` so cross-workspace
access is structurally impossible (BR9). Timestamps default to the injected
clock (falling back to :func:`utc_now_iso`) when the caller omits one.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.models import Artifact
from ....errors import ErrorCode, OktoNexusError


def _db_error(action: str, exc: sqlite3.Error) -> OktoNexusError:
    return OktoNexusError(
        ErrorCode.DB_ERROR,
        f"SQLite failure while {action}.",
        {"reason": str(exc)},
    )


class SqliteArtifactRepo:
    """Persistence for ``artifacts`` rows (inline content or path references)."""

    _COLUMNS = (
        "artifact_id, workspace_id, artifact_type, name, path, content, "
        "size_bytes, content_type, created_at"
    )

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock.now_iso()
        return utc_now_iso()

    def create(
        self,
        uow: UnitOfWork,
        *,
        artifact_id: str,
        workspace_id: str,
        artifact_type: str,
        name: str | None = None,
        path: str | None = None,
        content: str | None = None,
        size_bytes: int | None = None,
        content_type: str | None = None,
        created_at: str | None = None,
    ) -> Artifact:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO artifacts
                    (artifact_id, workspace_id, artifact_type, name, path,
                     content, size_bytes, content_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    workspace_id,
                    artifact_type,
                    name,
                    path,
                    content,
                    size_bytes,
                    content_type,
                    now,
                ),
            )
        except sqlite3.Error as exc:
            raise _db_error("creating artifact", exc) from exc
        row = self.get(uow, workspace_id=workspace_id, artifact_id=artifact_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Artifact missing immediately after insert.",
                {"artifact_id": artifact_id},
            )
        return row

    def get(
        self, uow: UnitOfWork, *, workspace_id: str, artifact_id: str
    ) -> Artifact | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM artifacts "
                "WHERE workspace_id = ? AND artifact_id = ?",
                (workspace_id, artifact_id),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading artifact", exc) from exc
        if row is None:
            return None
        return self._row_to_artifact(row)

    def list(
        self, uow: UnitOfWork, *, workspace_id: str, artifact_type: str | None = None
    ) -> list[Artifact]:
        sql = f"SELECT {self._COLUMNS} FROM artifacts WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if artifact_type is not None:
            sql += " AND artifact_type = ?"
            params.append(artifact_type)
        sql += " ORDER BY created_at, artifact_id"
        try:
            cur = uow.connection.execute(sql, tuple(params))
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing artifacts", exc) from exc
        return [self._row_to_artifact(row) for row in rows]

    @staticmethod
    def _row_to_artifact(row: Any) -> Artifact:
        return Artifact(
            artifact_id=row["artifact_id"],
            workspace_id=row["workspace_id"],
            artifact_type=row["artifact_type"],
            created_at=row["created_at"],
            name=row["name"],
            path=row["path"],
            content=row["content"],
            size_bytes=row["size_bytes"],
            content_type=row["content_type"],
        )
