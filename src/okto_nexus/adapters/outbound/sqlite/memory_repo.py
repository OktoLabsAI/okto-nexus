"""SQLite repositories for the workspace memory slice (spec 8928b320, I6).

Concrete implementations of :class:`okto_nexus.application.ports.MemoryRepo`
and :class:`okto_nexus.application.ports.MemoryVectorStore`. Every method
operates on ``uow.connection`` inside the caller's active transaction so the
row, the supersede stamp and the ``memory.*`` event commit atomically.

Outbound adapter: it MAY import ``sqlite3`` and the domain dataclasses.
Reads are always scoped by ``workspace_id`` so cross-workspace access is
structurally impossible. ``topics`` is (de)serialised to a JSON array here -
the domain and the service only ever see a native ``list[str]``.

The vector store mirrors :class:`SqliteMessageVectorStore` byte-for-byte
(little-endian float32 BLOB, stdlib cosine, dim guard in SQL - br_04f0e599):
one proven byte layout for every embedding table in the schema.
"""

from __future__ import annotations

import json
import math
import sqlite3
import struct
from typing import Any, Optional, Sequence

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.models import Memory
from ....errors import OktoNexusError, db_error_from_exception


def _db_error(action: str, exc: sqlite3.Error) -> OktoNexusError:
    return db_error_from_exception(action, exc)


def _like_pattern(term: str) -> str:
    """Build a substring LIKE pattern with ``%``/``_``/escape neutralised."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class SqliteMemoryRepo:
    """Persistence for ``memories`` rows (append-only + supersede stamping)."""

    _COLUMNS = (
        "memory_id, workspace_id, author_agent_id, title, content, topics, "
        "source_kind, source_id, supersedes, superseded_by, trace_id, created_at"
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
        memory_id: str,
        workspace_id: str,
        author_agent_id: str,
        title: str,
        content: str,
        topics: Sequence[str] = (),
        source_kind: str | None = None,
        source_id: str | None = None,
        supersedes: str | None = None,
        trace_id: str | None = None,
        created_at: str | None = None,
    ) -> Memory:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO memories
                    (memory_id, workspace_id, author_agent_id, title, content,
                     topics, source_kind, source_id, supersedes, superseded_by,
                     trace_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    memory_id,
                    workspace_id,
                    author_agent_id,
                    title,
                    content,
                    json.dumps(list(topics), ensure_ascii=False),
                    source_kind,
                    source_id,
                    supersedes,
                    trace_id,
                    now,
                ),
            )
        except sqlite3.Error as exc:
            raise _db_error("creating memory", exc) from exc
        return Memory(
            memory_id=memory_id,
            workspace_id=workspace_id,
            author_agent_id=author_agent_id,
            title=title,
            content=content,
            created_at=now,
            topics=list(topics),
            source_kind=source_kind,
            source_id=source_id,
            supersedes=supersedes,
            superseded_by=None,
            trace_id=trace_id,
        )

    def get(
        self, uow: UnitOfWork, *, workspace_id: str, memory_id: str
    ) -> Memory | None:
        try:
            row = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM memories "
                "WHERE workspace_id = ? AND memory_id = ?",
                (workspace_id, memory_id),
            ).fetchone()
        except sqlite3.Error as exc:
            raise _db_error("reading memory", exc) from exc
        if row is None:
            return None
        return self._row_to_memory(row)

    def get_many(
        self, uow: UnitOfWork, *, workspace_id: str, memory_ids: Sequence[str]
    ) -> dict[str, Memory]:
        """Fetch several rows at once (semantic re-rank id -> row mapping)."""
        ids = [str(mid) for mid in memory_ids]
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        try:
            rows = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM memories "
                f"WHERE workspace_id = ? AND memory_id IN ({placeholders})",
                (workspace_id, *ids),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("reading memories", exc) from exc
        result = {}
        for row in rows:
            memory = self._row_to_memory(row)
            result[memory.memory_id] = memory
        return result

    def list(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        include_superseded: bool = False,
        topic: str | None = None,
        author_agent_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Memory]:
        """Newest-first browse; live-only unless ``include_superseded``."""
        sql = f"SELECT {self._COLUMNS} FROM memories WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if not include_superseded:
            sql += " AND superseded_by IS NULL"
        if topic is not None:
            # topics is a JSON array of lowercase strings: every element is
            # quoted, so an exact-token match is a quoted substring match.
            sql += " AND topics LIKE ?"
            params.append(f'%"{topic}"%')
        if author_agent_id is not None:
            sql += " AND author_agent_id = ?"
            params.append(author_agent_id)
        sql += " ORDER BY created_at DESC, memory_id LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
        try:
            rows = uow.connection.execute(sql, tuple(params)).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("listing memories", exc) from exc
        return [self._row_to_memory(row) for row in rows]

    def search_lexical(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        query: str,
        include_superseded: bool = False,
        topic: str | None = None,
        limit: int = 50,
    ) -> list[Memory]:
        """Deterministic substring match over title+content+topics (FR4).

        Case-insensitive for ASCII (SQLite ``LIKE`` default); ``%``/``_`` in
        the query are neutralised so user input is always a literal term.
        Newest first - the lexical mode ranks by recency, never by score.
        """
        pattern = _like_pattern(query)
        sql = (
            f"SELECT {self._COLUMNS} FROM memories WHERE workspace_id = ? "
            "AND (title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\' "
            "OR topics LIKE ? ESCAPE '\\')"
        )
        params: list[Any] = [workspace_id, pattern, pattern, pattern]
        if not include_superseded:
            sql += " AND superseded_by IS NULL"
        if topic is not None:
            sql += " AND topics LIKE ?"
            params.append(f'%"{topic}"%')
        sql += " ORDER BY created_at DESC, memory_id LIMIT ?"
        params.append(int(limit))
        try:
            rows = uow.connection.execute(sql, tuple(params)).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("searching memories", exc) from exc
        return [self._row_to_memory(row) for row in rows]

    def mark_superseded(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        memory_id: str,
        superseded_by: str,
    ) -> int:
        """Stamp ``superseded_by`` on a live target row; return rows changed.

        The ``superseded_by IS NULL`` guard makes the stamp exactly-once at
        the SQL level: a concurrent second supersede matches zero rows (WAL
        serialises writers, BR4) and the service maps 0 to ``CONFLICT``.
        """
        try:
            cur = uow.connection.execute(
                "UPDATE memories SET superseded_by = ? "
                "WHERE workspace_id = ? AND memory_id = ? "
                "AND superseded_by IS NULL",
                (superseded_by, workspace_id, memory_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("superseding memory", exc) from exc
        return int(cur.rowcount)

    def delete(self, uow: UnitOfWork, *, workspace_id: str, memory_id: str) -> int:
        """Physically remove a row (operator curation only); rows removed.

        The vector goes with it via ``ON DELETE CASCADE`` (D-EMB-5).
        """
        try:
            cur = uow.connection.execute(
                "DELETE FROM memories WHERE workspace_id = ? AND memory_id = ?",
                (workspace_id, memory_id),
            )
        except sqlite3.Error as exc:
            raise _db_error("deleting memory", exc) from exc
        return int(cur.rowcount)

    @staticmethod
    def _row_to_memory(row: Any) -> Memory:
        try:
            topics = json.loads(row["topics"]) if row["topics"] else []
        except (TypeError, ValueError):  # pragma: no cover - defensive
            topics = []
        if not isinstance(topics, list):  # pragma: no cover - defensive
            topics = []
        return Memory(
            memory_id=row["memory_id"],
            workspace_id=row["workspace_id"],
            author_agent_id=row["author_agent_id"],
            title=row["title"],
            content=row["content"],
            created_at=row["created_at"],
            topics=[str(t) for t in topics],
            source_kind=row["source_kind"],
            source_id=row["source_id"],
            supersedes=row["supersedes"],
            superseded_by=row["superseded_by"],
            trace_id=row["trace_id"],
        )


def _pack_vector(vector: Sequence[float]) -> bytes:
    """Serialise a float vector as little-endian float32 (4 bytes each)."""
    values = [float(component) for component in vector]
    return struct.pack(f"<{len(values)}f", *values)


def _unpack_vector(blob: bytes) -> list[float]:
    """Inverse of :func:`_pack_vector` (length inferred from the BLOB size)."""
    count = len(blob) // 4
    if count == 0:
        return []
    return list(struct.unpack(f"<{count}f", blob[: count * 4]))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity in pure Python; ``0.0`` for a zero-magnitude vector."""
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


class SqliteMemoryVectorStore:
    """Persistence + cosine retrieval for ``memory_embeddings`` rows."""

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock.now_iso()
        return utc_now_iso()

    def upsert(
        self,
        uow: UnitOfWork,
        *,
        memory_id: str,
        vector: Sequence[float],
        model: str,
        dim: int,
        created_at: str | None = None,
    ) -> None:
        """Insert or replace the vector for ``memory_id`` (idempotent by id)."""
        now = created_at or self._now()
        blob = _pack_vector(vector)
        try:
            uow.connection.execute(
                """
                INSERT INTO memory_embeddings
                    (memory_id, vec, model, dim, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    vec = excluded.vec,
                    model = excluded.model,
                    dim = excluded.dim,
                    created_at = excluded.created_at
                """,
                (memory_id, blob, model, int(dim), now),
            )
        except sqlite3.Error as exc:
            raise _db_error("storing memory embedding", exc) from exc

    def search(
        self, uow: UnitOfWork, *, query_vector: Sequence[float], k: int
    ) -> list[tuple[str, float]]:
        """Return up to ``k`` ``(memory_id, cosine)`` pairs, highest first.

        Only rows whose ``dim`` matches the query are considered (the SQL
        filter), so incompatible-shape vectors are skipped, never compared.
        """
        query = [float(component) for component in query_vector]
        limit = max(1, int(k))
        if not query:
            return []
        try:
            rows = uow.connection.execute(
                "SELECT memory_id, vec FROM memory_embeddings WHERE dim = ?",
                (len(query),),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("searching memory embeddings", exc) from exc
        scored: list[tuple[str, float]] = [
            (row["memory_id"], _cosine(query, _unpack_vector(row["vec"])))
            for row in rows
        ]
        # Highest cosine first; ties broken by memory_id for a stable order.
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:limit]

    def delete(self, uow: UnitOfWork, *, memory_id: str) -> int:
        """Delete the vector for ``memory_id``; return rows removed (0 or 1)."""
        try:
            cur = uow.connection.execute(
                "DELETE FROM memory_embeddings WHERE memory_id = ?",
                (memory_id,),
            )
        except sqlite3.Error as exc:
            raise _db_error("deleting memory embedding", exc) from exc
        return int(cur.rowcount)
