"""SQLite repository for the central tag catalog (migration 013).

Concrete :class:`TagCatalogRepo` implementation over ``tag_keys`` /
``tag_values``. The catalog is the single registry behind the fail-closed
tag-scoping rule: a key/value pair may only be referenced (agent tags,
comm_scope selectors, ``strategy: "tag"`` targets) after it exists here.
EXISTENCE checks and the in-use deletion guard (``TAG_IN_USE``) live in the
application layer (:mod:`okto_nexus.application.tags`); this repo persists.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.models import TagKey, TagValue
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


class SqliteTagCatalogRepo:
    """Persistence for ``tag_keys`` / ``tag_values`` rows."""

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        return self._clock.now_iso() if self._clock is not None else utc_now_iso()

    # ------------------------------------------------------------------ #
    # Keys
    # ------------------------------------------------------------------ #
    def create_key(
        self, uow: UnitOfWork, *, key: str, description: str | None = None
    ) -> TagKey:
        try:
            uow.connection.execute(
                "INSERT INTO tag_keys (key, description, created_at) VALUES (?, ?, ?)",
                (key, description, self._now()),
            )
        except sqlite3.IntegrityError as exc:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"Tag key '{key}' is already registered.",
                {"key": key},
            ) from exc
        except sqlite3.Error as exc:
            raise db_error_from_exception("creating tag key", exc) from exc
        row = self.get_key(uow, key)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Tag key missing immediately after insert.",
                {"key": key},
            )
        return row

    def get_key(self, uow: UnitOfWork, key: str) -> TagKey | None:
        try:
            cur = uow.connection.execute(
                "SELECT key, description, created_at FROM tag_keys WHERE key = ?",
                (key,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading tag key", exc) from exc
        return None if row is None else self._row_to_key(row)

    def list_keys(self, uow: UnitOfWork) -> list[TagKey]:
        try:
            cur = uow.connection.execute(
                "SELECT key, description, created_at FROM tag_keys ORDER BY key"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing tag keys", exc) from exc
        return [self._row_to_key(row) for row in rows]

    def delete_key(self, uow: UnitOfWork, *, key: str) -> bool:
        """Delete a key (registered values cascade). True if it existed.

        The in-use guard is the APPLICATION layer's job (``TAG_IN_USE``);
        by the time this runs the key is known to be unreferenced.
        """
        try:
            cur = uow.connection.execute("DELETE FROM tag_keys WHERE key = ?", (key,))
        except sqlite3.Error as exc:
            raise db_error_from_exception("deleting tag key", exc) from exc
        return cur.rowcount > 0

    # ------------------------------------------------------------------ #
    # Values
    # ------------------------------------------------------------------ #
    def create_value(
        self,
        uow: UnitOfWork,
        *,
        key: str,
        value: str,
        description: str | None = None,
    ) -> TagValue:
        try:
            uow.connection.execute(
                "INSERT INTO tag_values (key, value, description, created_at) "
                "VALUES (?, ?, ?, ?)",
                (key, value, description, self._now()),
            )
        except sqlite3.IntegrityError as exc:
            # Disambiguate: an unregistered parent key (FK) vs a duplicate
            # value (PK) - both arrive as IntegrityError.
            if self.get_key(uow, key) is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"Tag key '{key}' is not registered; register the key "
                    "before adding values.",
                    {"key": key},
                ) from exc
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"Tag value '{key}={value}' is already registered.",
                {"key": key, "value": value},
            ) from exc
        except sqlite3.Error as exc:
            raise db_error_from_exception("creating tag value", exc) from exc
        row = self.get_value(uow, key=key, value=value)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Tag value missing immediately after insert.",
                {"key": key, "value": value},
            )
        return row

    def get_value(self, uow: UnitOfWork, *, key: str, value: str) -> TagValue | None:
        try:
            cur = uow.connection.execute(
                "SELECT key, value, description, created_at FROM tag_values "
                "WHERE key = ? AND value = ?",
                (key, value),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading tag value", exc) from exc
        return None if row is None else self._row_to_value(row)

    def list_values(self, uow: UnitOfWork, *, key: str | None = None) -> list[TagValue]:
        sql = "SELECT key, value, description, created_at FROM tag_values"
        params: tuple[Any, ...] = ()
        if key is not None:
            sql += " WHERE key = ?"
            params = (key,)
        sql += " ORDER BY key, value"
        try:
            cur = uow.connection.execute(sql, params)
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing tag values", exc) from exc
        return [self._row_to_value(row) for row in rows]

    def delete_value(self, uow: UnitOfWork, *, key: str, value: str) -> bool:
        """Delete one value. True if it existed (in-use guard is upstream)."""
        try:
            cur = uow.connection.execute(
                "DELETE FROM tag_values WHERE key = ? AND value = ?",
                (key, value),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("deleting tag value", exc) from exc
        return cur.rowcount > 0

    # ------------------------------------------------------------------ #
    # Row mappers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _row_to_key(row: Any) -> TagKey:
        return TagKey(
            key=row["key"],
            description=row["description"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_value(row: Any) -> TagValue:
        return TagValue(
            key=row["key"],
            value=row["value"],
            description=row["description"],
            created_at=row["created_at"],
        )
