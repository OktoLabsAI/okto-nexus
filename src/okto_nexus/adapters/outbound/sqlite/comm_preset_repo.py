"""SQLite repositories for communication presets (migration 023).

Two concrete adapters, the content-only, single-source twins of the policy
repos (:mod:`okto_nexus.adapters.outbound.sqlite.policy_repo`):

* :class:`SqliteCommPresetRepo` - the NAMED global preset catalog
  (:class:`okto_nexus.application.ports.CommPresetRepo`): the ``comm_presets``
  metadata row plus its append-only ``comm_preset_versions``. Publishing an
  edit APPENDS the next ``(preset_id, version)`` row; versions are immutable.
* :class:`SqliteAgentCommBindingRepo` - an agent's SINGLE binding
  (:class:`okto_nexus.application.ports.AgentCommBindingRepo`) in the
  ``agent_comm_binding`` table (PK ``agent_id``), so :meth:`set` is a one-row
  upsert and the ``COMM_PRESET_IN_USE`` guard is one indexed lookup.

Both follow the repo conventions: ``__init__`` takes only an optional clock,
every method is UoW-first + keyword-only, and the JSON ``content`` column is
(de)serialised here. Form validation is upstream in
:mod:`okto_nexus.domain.comm_preset`; these repos persist already-validated
values.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping, Optional

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.comm_preset import CommPresetRecord, CommPresetVersion
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception

_UNSET = "__unset__"


def _dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _loads(text: str | None) -> dict[str, str]:
    if text is None:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


class SqliteCommPresetRepo:
    """Persistence for ``comm_presets`` + append-only ``comm_preset_versions``."""

    _LATEST_SQL = (
        "COALESCE((SELECT MAX(version) FROM comm_preset_versions v "
        "WHERE v.preset_id = p.preset_id), 0) AS latest_version"
    )
    _RECORD_COLUMNS = (
        f"p.preset_id, p.name, p.description, p.created_at, p.updated_at, {_LATEST_SQL}"
    )
    _VERSION_COLUMNS = "preset_id, version, content, published_at"

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        return self._clock.now_iso() if self._clock is not None else utc_now_iso()

    # ------------------------------------------------------------------ #
    # Catalog CRUD
    # ------------------------------------------------------------------ #
    def create(
        self,
        uow: UnitOfWork,
        *,
        preset_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> CommPresetRecord:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO comm_presets (preset_id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (preset_id, name, description, now, now),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("creating communication preset", exc) from exc
        row = self.get(uow, preset_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Communication preset missing immediately after insert.",
                {"preset_id": preset_id},
            )
        return row

    def get(self, uow: UnitOfWork, preset_id: str) -> CommPresetRecord | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._RECORD_COLUMNS} FROM comm_presets p WHERE p.preset_id = ?",
                (preset_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading communication preset", exc) from exc
        return None if row is None else self._row_to_record(row)

    def get_by_name(self, uow: UnitOfWork, name: str) -> CommPresetRecord | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._RECORD_COLUMNS} FROM comm_presets p WHERE p.name = ?",
                (name,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "reading communication preset by name", exc
            ) from exc
        return None if row is None else self._row_to_record(row)

    def list(self, uow: UnitOfWork) -> list[CommPresetRecord]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._RECORD_COLUMNS} FROM comm_presets p "
                "ORDER BY p.created_at, p.preset_id"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing communication presets", exc) from exc
        return [self._row_to_record(row) for row in rows]

    def update(
        self,
        uow: UnitOfWork,
        *,
        preset_id: str,
        name: str | None = None,
        description: Any = _UNSET,
    ) -> CommPresetRecord | None:
        sets: list[str] = []
        params: list[Any] = []
        if name is not None:
            sets.append("name = ?")
            params.append(name)
        if description != _UNSET:
            sets.append("description = ?")
            params.append(description)
        if not sets:
            return self.get(uow, preset_id)
        sets.append("updated_at = ?")
        params.append(self._now())
        params.append(preset_id)
        try:
            cur = uow.connection.execute(
                f"UPDATE comm_presets SET {', '.join(sets)} WHERE preset_id = ?",
                tuple(params),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("updating communication preset", exc) from exc
        if cur.rowcount == 0:
            return None
        return self.get(uow, preset_id)

    def delete(self, uow: UnitOfWork, *, preset_id: str) -> bool:
        try:
            cur = uow.connection.execute(
                "DELETE FROM comm_presets WHERE preset_id = ?", (preset_id,)
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("deleting communication preset", exc) from exc
        return cur.rowcount > 0

    # ------------------------------------------------------------------ #
    # Append-only versions
    # ------------------------------------------------------------------ #
    def add_version(
        self,
        uow: UnitOfWork,
        *,
        preset_id: str,
        content: Mapping[str, Any],
        published_at: str | None = None,
    ) -> CommPresetVersion:
        now = published_at or self._now()
        try:
            row = uow.connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM comm_preset_versions "
                "WHERE preset_id = ?",
                (preset_id,),
            ).fetchone()
            next_version = int(row[0])
            uow.connection.execute(
                """
                INSERT INTO comm_preset_versions (preset_id, version, content, published_at)
                VALUES (?, ?, ?, ?)
                """,
                (preset_id, next_version, _dumps(dict(content)), now),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "appending communication preset version", exc
            ) from exc
        stored = self.get_version(uow, preset_id=preset_id, version=next_version)
        if stored is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Communication preset version missing immediately after insert.",
                {"preset_id": preset_id, "version": next_version},
            )
        return stored

    def get_version(
        self, uow: UnitOfWork, *, preset_id: str, version: int
    ) -> CommPresetVersion | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._VERSION_COLUMNS} FROM comm_preset_versions "
                "WHERE preset_id = ? AND version = ?",
                (preset_id, version),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "reading communication preset version", exc
            ) from exc
        return None if row is None else self._row_to_version(row)

    def latest_version(
        self, uow: UnitOfWork, *, preset_id: str
    ) -> CommPresetVersion | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._VERSION_COLUMNS} FROM comm_preset_versions "
                "WHERE preset_id = ? ORDER BY version DESC LIMIT 1",
                (preset_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "reading latest communication preset version", exc
            ) from exc
        return None if row is None else self._row_to_version(row)

    def list_versions(
        self, uow: UnitOfWork, *, preset_id: str
    ) -> list[CommPresetVersion]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._VERSION_COLUMNS} FROM comm_preset_versions "
                "WHERE preset_id = ? ORDER BY version ASC",
                (preset_id,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "listing communication preset versions", exc
            ) from exc
        return [self._row_to_version(row) for row in rows]

    # ------------------------------------------------------------------ #
    # Row mappers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _row_to_record(row: Any) -> CommPresetRecord:
        return CommPresetRecord(
            preset_id=row["preset_id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            latest_version=int(row["latest_version"]),
        )

    @staticmethod
    def _row_to_version(row: Any) -> CommPresetVersion:
        return CommPresetVersion(
            preset_id=row["preset_id"],
            version=int(row["version"]),
            content=_loads(row["content"]),
            published_at=row["published_at"],
        )


class SqliteAgentCommBindingRepo:
    """Persistence for ``agent_comm_binding`` (single-source, one row per agent)."""

    _COLUMNS = "agent_id, source, preset_id, mode, pinned_version, content, created_at"

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        return self._clock.now_iso() if self._clock is not None else utc_now_iso()

    def set(
        self, uow: UnitOfWork, *, agent_id: str, binding: Mapping[str, Any] | None
    ) -> None:
        try:
            # Full overwrite of the single row: delete then (re)insert. A None
            # binding leaves the agent with no row (back to today's whoami).
            uow.connection.execute(
                "DELETE FROM agent_comm_binding WHERE agent_id = ?", (agent_id,)
            )
            if binding is not None:
                content = binding.get("content")
                uow.connection.execute(
                    f"""
                    INSERT INTO agent_comm_binding ({self._COLUMNS})
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        agent_id,
                        binding["source"],
                        binding.get("preset_id"),
                        binding.get("mode"),
                        binding.get("pinned_version"),
                        _dumps(content) if content is not None else None,
                        self._now(),
                    ),
                )
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "setting agent communication binding", exc
            ) from exc

    def get(self, uow: UnitOfWork, *, agent_id: str) -> dict[str, Any] | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM agent_comm_binding WHERE agent_id = ?",
                (agent_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "reading agent communication binding", exc
            ) from exc
        return None if row is None else self._row_to_binding(row)

    def agents_binding_preset(self, uow: UnitOfWork, *, preset_id: str) -> list[str]:
        try:
            cur = uow.connection.execute(
                "SELECT DISTINCT agent_id FROM agent_comm_binding "
                "WHERE preset_id = ? ORDER BY agent_id",
                (preset_id,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "finding communication preset bindings", exc
            ) from exc
        return [row["agent_id"] for row in rows]

    @staticmethod
    def _row_to_binding(row: Any) -> dict[str, Any]:
        source = row["source"]
        binding: dict[str, Any] = {"source": source}
        if source == "inline":
            binding["content"] = _loads(row["content"])
        else:
            binding["preset_id"] = row["preset_id"]
            binding["mode"] = row["mode"]
            if row["mode"] == "pinned":
                binding["pinned_version"] = row["pinned_version"]
        return binding
