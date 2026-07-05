"""SQLite repositories for attachable, versioned policies (migration 022).

Two concrete adapters:

* :class:`SqlitePolicyRepo` - the NAMED global policy catalog
  (:class:`okto_nexus.application.ports.PolicyRepo`): the ``policies`` metadata
  row plus its append-only ``policy_versions``. Publishing an edit APPENDS the
  next ``(policy_id, version)`` row; versions are immutable.
* :class:`SqliteAgentPolicyBindingRepo` - an agent's ordered bindings
  (:class:`okto_nexus.application.ports.AgentPolicyBindingRepo`) in the
  ``agent_policy_bindings`` table, so the ``POLICY_IN_USE`` guard is one
  indexed lookup and :meth:`replace` is a full overwrite in a single UoW.

Both follow the repo conventions: ``__init__`` takes only an optional clock,
every method is UoW-first + keyword-only, and JSON columns (``audience`` /
``governance``) are (de)serialised here. Form validation is upstream in
:mod:`okto_nexus.domain.policy`; these repos persist already-validated values.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping, Optional, Sequence

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.policy import PolicyRecord, PolicyVersion
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception

_UNSET = "__unset__"


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


class SqlitePolicyRepo:
    """Persistence for ``policies`` + append-only ``policy_versions``."""

    _LATEST_SQL = (
        "COALESCE((SELECT MAX(version) FROM policy_versions v "
        "WHERE v.policy_id = p.policy_id), 0) AS latest_version"
    )
    _RECORD_COLUMNS = (
        f"p.policy_id, p.name, p.description, p.created_at, p.updated_at, {_LATEST_SQL}"
    )

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
        policy_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> PolicyRecord:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO policies (policy_id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (policy_id, name, description, now, now),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("creating policy", exc) from exc
        row = self.get(uow, policy_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Policy missing immediately after insert.",
                {"policy_id": policy_id},
            )
        return row

    def get(self, uow: UnitOfWork, policy_id: str) -> PolicyRecord | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._RECORD_COLUMNS} FROM policies p WHERE p.policy_id = ?",
                (policy_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading policy", exc) from exc
        return None if row is None else self._row_to_record(row)

    def get_by_name(self, uow: UnitOfWork, name: str) -> PolicyRecord | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._RECORD_COLUMNS} FROM policies p WHERE p.name = ?",
                (name,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading policy by name", exc) from exc
        return None if row is None else self._row_to_record(row)

    def list(self, uow: UnitOfWork) -> list[PolicyRecord]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._RECORD_COLUMNS} FROM policies p "
                "ORDER BY p.created_at, p.policy_id"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing policies", exc) from exc
        return [self._row_to_record(row) for row in rows]

    def update(
        self,
        uow: UnitOfWork,
        *,
        policy_id: str,
        name: str | None = None,
        description: Any = _UNSET,
    ) -> PolicyRecord | None:
        sets: list[str] = []
        params: list[Any] = []
        if name is not None:
            sets.append("name = ?")
            params.append(name)
        if description != _UNSET:
            sets.append("description = ?")
            params.append(description)
        if not sets:
            return self.get(uow, policy_id)
        sets.append("updated_at = ?")
        params.append(self._now())
        params.append(policy_id)
        try:
            cur = uow.connection.execute(
                f"UPDATE policies SET {', '.join(sets)} WHERE policy_id = ?",
                tuple(params),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("updating policy", exc) from exc
        if cur.rowcount == 0:
            return None
        return self.get(uow, policy_id)

    def delete(self, uow: UnitOfWork, *, policy_id: str) -> bool:
        try:
            cur = uow.connection.execute(
                "DELETE FROM policies WHERE policy_id = ?", (policy_id,)
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("deleting policy", exc) from exc
        return cur.rowcount > 0

    # ------------------------------------------------------------------ #
    # Append-only versions
    # ------------------------------------------------------------------ #
    def add_version(
        self,
        uow: UnitOfWork,
        *,
        policy_id: str,
        audience: Mapping[str, Any] | None,
        governance: Sequence[Mapping[str, Any]],
        published_at: str | None = None,
    ) -> PolicyVersion:
        now = published_at or self._now()
        try:
            row = uow.connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM policy_versions "
                "WHERE policy_id = ?",
                (policy_id,),
            ).fetchone()
            next_version = int(row[0])
            uow.connection.execute(
                """
                INSERT INTO policy_versions
                    (policy_id, version, audience, governance, published_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    policy_id,
                    next_version,
                    _dumps(audience),
                    _dumps(list(governance)),
                    now,
                ),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("appending policy version", exc) from exc
        stored = self.get_version(uow, policy_id=policy_id, version=next_version)
        if stored is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Policy version missing immediately after insert.",
                {"policy_id": policy_id, "version": next_version},
            )
        return stored

    def get_version(
        self, uow: UnitOfWork, *, policy_id: str, version: int
    ) -> PolicyVersion | None:
        try:
            cur = uow.connection.execute(
                "SELECT policy_id, version, audience, governance, published_at "
                "FROM policy_versions WHERE policy_id = ? AND version = ?",
                (policy_id, version),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading policy version", exc) from exc
        return None if row is None else self._row_to_version(row)

    def latest_version(
        self, uow: UnitOfWork, *, policy_id: str
    ) -> PolicyVersion | None:
        try:
            cur = uow.connection.execute(
                "SELECT policy_id, version, audience, governance, published_at "
                "FROM policy_versions WHERE policy_id = ? "
                "ORDER BY version DESC LIMIT 1",
                (policy_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading latest policy version", exc) from exc
        return None if row is None else self._row_to_version(row)

    def list_versions(self, uow: UnitOfWork, *, policy_id: str) -> list[PolicyVersion]:
        try:
            cur = uow.connection.execute(
                "SELECT policy_id, version, audience, governance, published_at "
                "FROM policy_versions WHERE policy_id = ? ORDER BY version ASC",
                (policy_id,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing policy versions", exc) from exc
        return [self._row_to_version(row) for row in rows]

    def versions_for(
        self, uow: UnitOfWork, *, policy_ids: Sequence[str]
    ) -> dict[str, list[PolicyVersion]]:
        ids = [pid for pid in dict.fromkeys(policy_ids)]  # de-dup, keep order
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        try:
            cur = uow.connection.execute(
                "SELECT policy_id, version, audience, governance, published_at "
                f"FROM policy_versions WHERE policy_id IN ({placeholders}) "
                "ORDER BY policy_id, version ASC",
                tuple(ids),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("bulk-reading policy versions", exc) from exc
        out: dict[str, list[PolicyVersion]] = {}
        for row in rows:
            out.setdefault(row["policy_id"], []).append(self._row_to_version(row))
        return out

    # ------------------------------------------------------------------ #
    # Row mappers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _row_to_record(row: Any) -> PolicyRecord:
        return PolicyRecord(
            policy_id=row["policy_id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            latest_version=int(row["latest_version"]),
        )

    @staticmethod
    def _row_to_version(row: Any) -> PolicyVersion:
        governance = _loads(row["governance"])
        return PolicyVersion(
            policy_id=row["policy_id"],
            version=int(row["version"]),
            audience=_loads(row["audience"]),
            governance=tuple(governance) if governance else (),
            published_at=row["published_at"],
        )


class SqliteAgentPolicyBindingRepo:
    """Persistence for ``agent_policy_bindings`` (ordered, full-overwrite)."""

    _COLUMNS = (
        "agent_id, position, source, policy_id, mode, pinned_version, "
        "audience, governance, created_at"
    )

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        return self._clock.now_iso() if self._clock is not None else utc_now_iso()

    def replace(
        self, uow: UnitOfWork, *, agent_id: str, bindings: Sequence[Mapping[str, Any]]
    ) -> None:
        now = self._now()
        try:
            uow.connection.execute(
                "DELETE FROM agent_policy_bindings WHERE agent_id = ?", (agent_id,)
            )
            for position, binding in enumerate(bindings):
                uow.connection.execute(
                    f"""
                    INSERT INTO agent_policy_bindings ({self._COLUMNS})
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        agent_id,
                        position,
                        binding["source"],
                        binding.get("policy_id"),
                        binding.get("mode"),
                        binding.get("pinned_version"),
                        _dumps(binding.get("audience")),
                        _dumps(binding.get("governance")),
                        now,
                    ),
                )
        except sqlite3.Error as exc:
            raise db_error_from_exception("replacing agent bindings", exc) from exc

    def list_for_agent(self, uow: UnitOfWork, *, agent_id: str) -> list[dict[str, Any]]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM agent_policy_bindings "
                "WHERE agent_id = ? ORDER BY position ASC",
                (agent_id,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing agent bindings", exc) from exc
        return [self._row_to_binding(row) for row in rows]

    def agents_binding_policy(self, uow: UnitOfWork, *, policy_id: str) -> list[str]:
        try:
            cur = uow.connection.execute(
                "SELECT DISTINCT agent_id FROM agent_policy_bindings "
                "WHERE policy_id = ? ORDER BY agent_id",
                (policy_id,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("finding policy bindings", exc) from exc
        return [row["agent_id"] for row in rows]

    @staticmethod
    def _row_to_binding(row: Any) -> dict[str, Any]:
        governance = _loads(row["governance"])
        return {
            "source": row["source"],
            "policy_id": row["policy_id"],
            "mode": row["mode"],
            "pinned_version": row["pinned_version"],
            "audience": _loads(row["audience"]),
            "governance": list(governance) if governance else [],
        }
