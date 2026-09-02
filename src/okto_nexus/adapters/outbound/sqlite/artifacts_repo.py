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

import json
import sqlite3
from typing import Any, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.models import Artifact
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


def _db_error(action: str, exc: sqlite3.Error) -> OktoNexusError:
    # Centralised classification: lock/busy contention => retryable=True.
    return db_error_from_exception(action, exc)


def _dumps(value: Any) -> str | None:
    """Serialise the audience snapshot to JSON TEXT (``None`` stays NULL)."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _loads(text: str | None) -> Any:
    """Hydrate a JSON TEXT column; a NULL or malformed blob reads as ``None``."""
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


class SqliteArtifactRepo:
    """Searchable metadata catalog for externally stored artifacts.

    The legacy ``path``/``content``/``content_type`` columns remain readable so
    databases created before migration 028 keep working.  New writes leave
    those payload columns NULL and point at an injected ArtifactStore instead.
    """

    _COLUMNS = (
        "artifact_id, workspace_id, artifact_type, name, path, content, "
        "size_bytes, content_type, created_by, created_at, audience, "
        "storage_path, storage_kind, filename, media_type"
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
        created_by: str | None = None,
        created_at: str | None = None,
        audience: list[Any] | None = None,
        storage_path: str | None = None,
        storage_kind: str | None = None,
        filename: str | None = None,
        media_type: str | None = None,
    ) -> Artifact:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO artifacts
                    (artifact_id, workspace_id, artifact_type, name, path,
                     content, size_bytes, content_type, created_by, created_at,
                     audience, storage_path, storage_kind, filename, media_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    created_by,
                    now,
                    _dumps(audience),
                    storage_path,
                    storage_kind,
                    filename,
                    media_type,
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

    def list_all(
        self, uow: UnitOfWork, *, artifact_type: str | None = None
    ) -> list[Artifact]:
        sql = f"SELECT {self._COLUMNS} FROM artifacts"
        params: list[Any] = []
        if artifact_type is not None:
            sql += " WHERE artifact_type = ?"
            params.append(artifact_type)
        sql += " ORDER BY created_at, artifact_id"
        try:
            cur = uow.connection.execute(sql, tuple(params))
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing artifacts", exc) from exc
        return [self._row_to_artifact(row) for row in rows]

    def browse_catalog(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None,
        artifact_type: str | None,
        producer_ids: list[str],
        created_from: str | None,
        created_to: str | None,
        query: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Artifact], int]:
        clauses: list[str] = []
        params: list[Any] = []
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        if artifact_type is not None:
            clauses.append("artifact_type = ?")
            params.append(artifact_type)
        if producer_ids:
            placeholders = ", ".join("?" for _ in producer_ids)
            clauses.append(f"created_by IN ({placeholders})")
            params.extend(producer_ids)
        if created_from is not None:
            clauses.append("created_at >= ?")
            params.append(created_from)
        if created_to is not None:
            clauses.append("created_at <= ?")
            params.append(created_to)
        if query:
            clauses.append(
                "(LOWER(artifact_id) LIKE ? OR LOWER(COALESCE(name, '')) LIKE ? "
                "OR LOWER(COALESCE(filename, '')) LIKE ? "
                "OR LOWER(COALESCE(created_by, '')) LIKE ? "
                "OR LOWER(workspace_id) LIKE ?)"
            )
            like = f"%{query.lower()}%"
            params.extend([like, like, like, like, like])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            total = int(
                uow.connection.execute(
                    f"SELECT COUNT(*) FROM artifacts{where}", tuple(params)
                ).fetchone()[0]
            )
            rows = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM artifacts{where} "
                "ORDER BY created_at DESC, artifact_id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("browsing artifact catalog", exc) from exc
        return [self._row_to_artifact(row) for row in rows], total

    def list_legacy(self, uow: UnitOfWork) -> list[Artifact]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM artifacts "
                "WHERE storage_path IS NULL "
                "AND (content IS NOT NULL OR path IS NOT NULL) "
                "ORDER BY created_at, artifact_id"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing legacy artifacts", exc) from exc
        return [self._row_to_artifact(row) for row in rows]

    def set_external_storage(
        self,
        uow: UnitOfWork,
        *,
        artifact_id: str,
        storage_path: str,
        storage_kind: str,
        filename: str,
        media_type: str,
        size_bytes: int,
    ) -> None:
        try:
            cur = uow.connection.execute(
                """
                UPDATE artifacts
                SET storage_path = ?, storage_kind = ?, filename = ?,
                    media_type = ?, size_bytes = ?,
                    path = NULL, content = NULL, content_type = NULL
                WHERE artifact_id = ? AND storage_path IS NULL
                """,
                (
                    storage_path,
                    storage_kind,
                    filename,
                    media_type,
                    size_bytes,
                    artifact_id,
                ),
            )
        except sqlite3.Error as exc:
            raise _db_error("externalising legacy artifact", exc) from exc
        if cur.rowcount != 1:
            raise OktoNexusError(
                ErrorCode.CONFLICT,
                "Artifact was externalised concurrently.",
                {"artifact_id": artifact_id},
            )

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
            created_by=row["created_by"],
            audience=_loads(row["audience"]),
            storage_path=row["storage_path"],
            storage_kind=row["storage_kind"],
            filename=row["filename"],
            media_type=row["media_type"],
        )
