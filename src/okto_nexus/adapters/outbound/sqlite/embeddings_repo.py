"""SQLite outbound adapter for the message vector store (Frente 3).

Concrete :class:`MessageVectorStore`: persists each message embedding as a
little-endian ``float32`` BLOB in ``message_embeddings`` and ranks by cosine
similarity in pure Python (brute force over a small set - only NEW messages are
embedded; decision D-EMB-3). An outbound adapter, so it MAY import ``sqlite3``;
the (de)serialisation lives here so the domain never sees a byte layout.

Cosine is computed with the stdlib ``math`` only (no numpy), so it works
identically under the stub provider and the optional sentence-transformers
extra (rule TR6). Rows whose stored ``dim`` differs from the query's are
filtered out in SQL, so a model/provider change never mixes incompatible
vectors into a ranking (rule br_04f0e599).
"""

from __future__ import annotations

import math
import sqlite3
import struct
from typing import Sequence

from ....application.ports import UnitOfWork
from ....domain.base import utc_now_iso
from ....errors import OktoNexusError, db_error_from_exception


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


def _db_error(action: str, exc: sqlite3.Error) -> OktoNexusError:
    return db_error_from_exception(action, exc)


class SqliteMessageVectorStore:
    """Persistence + cosine retrieval for ``message_embeddings`` rows."""

    def __init__(self, clock=None) -> None:
        self._clock = clock

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock.now_iso()
        return utc_now_iso()

    def upsert(
        self,
        uow: UnitOfWork,
        *,
        message_id: str,
        vector: Sequence[float],
        model: str,
        dim: int,
        created_at: str | None = None,
    ) -> None:
        """Insert or replace the vector for ``message_id`` (idempotent by id)."""
        now = created_at or self._now()
        blob = _pack_vector(vector)
        try:
            uow.connection.execute(
                """
                INSERT INTO message_embeddings
                    (message_id, vec, model, dim, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    vec = excluded.vec,
                    model = excluded.model,
                    dim = excluded.dim,
                    created_at = excluded.created_at
                """,
                (message_id, blob, model, int(dim), now),
            )
        except sqlite3.Error as exc:
            raise _db_error("storing message embedding", exc) from exc

    def search(
        self, uow: UnitOfWork, *, query_vector: Sequence[float], k: int
    ) -> list[tuple[str, float]]:
        """Return up to ``k`` ``(message_id, cosine)`` pairs, highest first.

        Only rows whose ``dim`` matches the query are considered (the SQL
        filter), so incompatible-shape vectors are skipped, never compared.
        """
        query = [float(component) for component in query_vector]
        limit = max(1, int(k))
        if not query:
            return []
        try:
            rows = uow.connection.execute(
                "SELECT message_id, vec FROM message_embeddings WHERE dim = ?",
                (len(query),),
            ).fetchall()
        except sqlite3.Error as exc:
            raise _db_error("searching message embeddings", exc) from exc
        scored: list[tuple[str, float]] = [
            (row["message_id"], _cosine(query, _unpack_vector(row["vec"])))
            for row in rows
        ]
        # Highest cosine first; ties broken by message_id for a stable order.
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:limit]

    def delete(self, uow: UnitOfWork, *, message_id: str) -> int:
        """Delete the vector for ``message_id``; return rows removed (0 or 1)."""
        try:
            cur = uow.connection.execute(
                "DELETE FROM message_embeddings WHERE message_id = ?",
                (message_id,),
            )
        except sqlite3.Error as exc:
            raise _db_error("deleting message embedding", exc) from exc
        return int(cur.rowcount)
