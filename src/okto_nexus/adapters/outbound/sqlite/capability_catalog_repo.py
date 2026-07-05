"""SQLite repository for the central capability catalog (migration 014).

Concrete :class:`CapabilityCatalogRepo` implementation over
``capability_names``. The catalog is the single registry behind the
fail-closed capability rule: a name may only be referenced (agent
``capabilities``, ``strategy: "capability"`` targets) after it exists here.
EXISTENCE checks and the in-use deletion guard (``CAPABILITY_IN_USE``) live in
the application layer (:mod:`okto_nexus.application.capabilities`); this repo
persists.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.models import CapabilityName
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


class SqliteCapabilityCatalogRepo:
    """Persistence for ``capability_names`` rows."""

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        return self._clock.now_iso() if self._clock is not None else utc_now_iso()

    def create(
        self, uow: UnitOfWork, *, name: str, description: str | None = None
    ) -> CapabilityName:
        try:
            uow.connection.execute(
                "INSERT INTO capability_names (name, description, created_at) "
                "VALUES (?, ?, ?)",
                (name, description, self._now()),
            )
        except sqlite3.IntegrityError as exc:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"Capability '{name}' is already registered.",
                {"name": name},
            ) from exc
        except sqlite3.Error as exc:
            raise db_error_from_exception("creating capability", exc) from exc
        row = self.get(uow, name)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Capability missing immediately after insert.",
                {"name": name},
            )
        return row

    def ensure(self, uow: UnitOfWork, *, name: str) -> bool:
        """Insert-or-ignore (seed path): never overwrites an existing row."""
        try:
            cur = uow.connection.execute(
                "INSERT OR IGNORE INTO capability_names "
                "(name, description, created_at) VALUES (?, ?, ?)",
                (name, None, self._now()),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("seeding capability", exc) from exc
        return cur.rowcount > 0

    def get(self, uow: UnitOfWork, name: str) -> CapabilityName | None:
        try:
            cur = uow.connection.execute(
                "SELECT name, description, created_at FROM capability_names "
                "WHERE name = ?",
                (name,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading capability", exc) from exc
        return None if row is None else self._row_to_name(row)

    def list(self, uow: UnitOfWork) -> list[CapabilityName]:
        try:
            cur = uow.connection.execute(
                "SELECT name, description, created_at FROM capability_names "
                "ORDER BY name"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing capabilities", exc) from exc
        return [self._row_to_name(row) for row in rows]

    def delete(self, uow: UnitOfWork, *, name: str) -> bool:
        """Delete one name. True if it existed (in-use guard is upstream)."""
        try:
            cur = uow.connection.execute(
                "DELETE FROM capability_names WHERE name = ?", (name,)
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("deleting capability", exc) from exc
        return cur.rowcount > 0

    @staticmethod
    def _row_to_name(row: Any) -> CapabilityName:
        return CapabilityName(
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
        )
