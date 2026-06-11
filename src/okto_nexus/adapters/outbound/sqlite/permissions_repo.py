"""SQLite repository for CUSTOM permission presets (migration 011).

Concrete :class:`PresetRepo` implementation. Built-in presets never touch this
table - they live in :mod:`okto_nexus.domain.permissions` as code and are
read-only by construction; this repo persists only the operator-authored ones.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.models import PermissionPreset
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


class SqlitePresetRepo:
    """Persistence for ``permission_presets`` rows (custom presets only)."""

    _COLUMNS = "preset_id, name, description, flags, created_at, updated_at"

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        return self._clock.now_iso() if self._clock is not None else utc_now_iso()

    def create(
        self,
        uow: UnitOfWork,
        *,
        preset_id: str,
        name: str,
        flags: dict[str, Any],
        description: str | None = None,
    ) -> PermissionPreset:
        now = self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO permission_presets
                    (preset_id, name, description, flags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    preset_id,
                    name,
                    description,
                    json.dumps(flags, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"A preset named '{name}' already exists.",
                {"name": name},
            ) from exc
        except sqlite3.Error as exc:
            raise db_error_from_exception("creating preset", exc) from exc
        row = self.get(uow, preset_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Preset missing immediately after insert.",
                {"preset_id": preset_id},
            )
        return row

    def get(self, uow: UnitOfWork, preset_id: str) -> PermissionPreset | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM permission_presets WHERE preset_id = ?",
                (preset_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading preset", exc) from exc
        return None if row is None else self._row_to_preset(row)

    def list(self, uow: UnitOfWork) -> list[PermissionPreset]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM permission_presets ORDER BY name"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing presets", exc) from exc
        return [self._row_to_preset(row) for row in rows]

    def update(
        self,
        uow: UnitOfWork,
        *,
        preset_id: str,
        name: str | None = None,
        description: Any = "__unset__",
        flags: dict[str, Any] | None = None,
    ) -> PermissionPreset | None:
        existing = self.get(uow, preset_id)
        if existing is None:
            return None
        new_name = name if name is not None else existing.name
        new_description = (
            existing.description if description == "__unset__" else description
        )
        new_flags = flags if flags is not None else existing.flags
        try:
            uow.connection.execute(
                """
                UPDATE permission_presets
                SET name = ?, description = ?, flags = ?, updated_at = ?
                WHERE preset_id = ?
                """,
                (
                    new_name,
                    new_description,
                    json.dumps(new_flags, ensure_ascii=False),
                    self._now(),
                    preset_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"A preset named '{new_name}' already exists.",
                {"name": new_name},
            ) from exc
        except sqlite3.Error as exc:
            raise db_error_from_exception("updating preset", exc) from exc
        return self.get(uow, preset_id)

    def delete(self, uow: UnitOfWork, *, preset_id: str) -> bool:
        try:
            cur = uow.connection.execute(
                "DELETE FROM permission_presets WHERE preset_id = ?", (preset_id,)
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("deleting preset", exc) from exc
        return cur.rowcount > 0

    @staticmethod
    def _row_to_preset(row: Any) -> PermissionPreset:
        try:
            flags = json.loads(row["flags"])
        except (TypeError, ValueError):
            flags = {}
        return PermissionPreset(
            preset_id=row["preset_id"],
            name=row["name"],
            description=row["description"],
            flags=flags if isinstance(flags, dict) else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
