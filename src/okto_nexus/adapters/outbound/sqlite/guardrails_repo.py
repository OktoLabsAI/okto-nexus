"""SQLite repositories for communication guardrails and agent groups."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping, Optional, Sequence

from ....application.ports import Clock, UnitOfWork
from ....domain.base import utc_now_iso
from ....domain.guardrails import (
    RESOLUTION_CONFIG_UNAVAILABLE,
    VERSION_STATUSES,
    AgentGroupMember,
    AgentGroupRecord,
    EffectiveGuardrail,
    GuardrailAssignment,
    GuardrailRecord,
    GuardrailVersion,
    resolve_effective_guardrails,
    validate_guardrail_assignment_form,
    validate_guardrail_version_form,
)
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception

_UNSET = "__unset__"


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads(text: str | None) -> Any:
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _loads_dict(text: str | None) -> dict[str, Any]:
    parsed = _loads(text)
    return dict(parsed) if isinstance(parsed, dict) else {}


def _loads_tuple(text: str | None) -> tuple[str, ...]:
    parsed = _loads(text)
    if not isinstance(parsed, Sequence) or isinstance(parsed, (str, bytes, bytearray)):
        return ()
    return tuple(str(item) for item in parsed)


class SqliteAgentGroupRepo:
    """Persistence for ``agent_groups`` and ``agent_group_members``."""

    _GROUP_COLUMNS = "group_id, name, description, created_at, updated_at"
    _MEMBER_COLUMNS = "group_id, agent_id, created_at"

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        return self._clock.now_iso() if self._clock is not None else utc_now_iso()

    def create(
        self,
        uow: UnitOfWork,
        *,
        group_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> AgentGroupRecord:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO agent_groups
                    (group_id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (group_id, name, description, now, now),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("creating agent group", exc) from exc
        row = self.get(uow, group_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Agent group missing immediately after insert.",
                {"group_id": group_id},
            )
        return row

    def get(self, uow: UnitOfWork, group_id: str) -> AgentGroupRecord | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._GROUP_COLUMNS} FROM agent_groups WHERE group_id = ?",
                (group_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading agent group", exc) from exc
        return None if row is None else self._row_to_group(row)

    def get_by_name(self, uow: UnitOfWork, name: str) -> AgentGroupRecord | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._GROUP_COLUMNS} FROM agent_groups WHERE name = ?",
                (name,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading agent group by name", exc) from exc
        return None if row is None else self._row_to_group(row)

    def list(self, uow: UnitOfWork) -> list[AgentGroupRecord]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._GROUP_COLUMNS} FROM agent_groups "
                "ORDER BY created_at, group_id"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing agent groups", exc) from exc
        return [self._row_to_group(row) for row in rows]

    def update(
        self,
        uow: UnitOfWork,
        *,
        group_id: str,
        name: str | None = None,
        description: Any = _UNSET,
    ) -> AgentGroupRecord | None:
        sets: list[str] = []
        params: list[Any] = []
        if name is not None:
            sets.append("name = ?")
            params.append(name)
        if description != _UNSET:
            sets.append("description = ?")
            params.append(description)
        if not sets:
            return self.get(uow, group_id)
        sets.append("updated_at = ?")
        params.append(self._now())
        params.append(group_id)
        try:
            cur = uow.connection.execute(
                f"UPDATE agent_groups SET {', '.join(sets)} WHERE group_id = ?",
                tuple(params),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("updating agent group", exc) from exc
        if cur.rowcount == 0:
            return None
        return self.get(uow, group_id)

    def delete(self, uow: UnitOfWork, *, group_id: str) -> bool:
        try:
            cur = uow.connection.execute(
                "DELETE FROM agent_groups WHERE group_id = ?", (group_id,)
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("deleting agent group", exc) from exc
        return cur.rowcount > 0

    def add_member(
        self,
        uow: UnitOfWork,
        *,
        group_id: str,
        agent_id: str,
        created_at: str | None = None,
    ) -> AgentGroupMember:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT OR IGNORE INTO agent_group_members
                    (group_id, agent_id, created_at)
                VALUES (?, ?, ?)
                """,
                (group_id, agent_id, now),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("adding agent group member", exc) from exc
        row = self.get_member(uow, group_id=group_id, agent_id=agent_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Agent group member missing immediately after insert.",
                {"group_id": group_id, "agent_id": agent_id},
            )
        return row

    def get_member(
        self, uow: UnitOfWork, *, group_id: str, agent_id: str
    ) -> AgentGroupMember | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._MEMBER_COLUMNS} FROM agent_group_members "
                "WHERE group_id = ? AND agent_id = ?",
                (group_id, agent_id),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading agent group member", exc) from exc
        return None if row is None else self._row_to_member(row)

    def remove_member(self, uow: UnitOfWork, *, group_id: str, agent_id: str) -> bool:
        try:
            cur = uow.connection.execute(
                "DELETE FROM agent_group_members WHERE group_id = ? AND agent_id = ?",
                (group_id, agent_id),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("removing agent group member", exc) from exc
        return cur.rowcount > 0

    def list_members(self, uow: UnitOfWork, *, group_id: str) -> list[AgentGroupMember]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._MEMBER_COLUMNS} FROM agent_group_members "
                "WHERE group_id = ? ORDER BY agent_id",
                (group_id,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing agent group members", exc) from exc
        return [self._row_to_member(row) for row in rows]

    def groups_for_agent(self, uow: UnitOfWork, *, agent_id: str) -> list[str]:
        try:
            cur = uow.connection.execute(
                "SELECT group_id FROM agent_group_members WHERE agent_id = ? "
                "ORDER BY group_id",
                (agent_id,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing agent group ids", exc) from exc
        return [row["group_id"] for row in rows]

    @staticmethod
    def _row_to_group(row: Any) -> AgentGroupRecord:
        return AgentGroupRecord(
            group_id=row["group_id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_member(row: Any) -> AgentGroupMember:
        return AgentGroupMember(
            group_id=row["group_id"],
            agent_id=row["agent_id"],
            created_at=row["created_at"],
        )


class SqliteGuardrailRepo:
    """Persistence for ``guardrails`` and ``guardrail_versions``."""

    _LATEST_SQL = (
        "COALESCE((SELECT MAX(version) FROM guardrail_versions v "
        "WHERE v.guardrail_id = g.guardrail_id), 0) AS latest_version"
    )
    _LATEST_ACTIVE_SQL = (
        "(SELECT MAX(version) FROM guardrail_versions v "
        "WHERE v.guardrail_id = g.guardrail_id AND v.status = 'active') "
        "AS latest_active_version"
    )
    _RECORD_COLUMNS = (
        "g.guardrail_id, g.name, g.description, g.created_at, g.updated_at, "
        f"{_LATEST_SQL}, {_LATEST_ACTIVE_SQL}"
    )
    _VERSION_COLUMNS = (
        "guardrail_id, version, status, evaluator_kind, evaluator_config, "
        "surfaces, field_targets, created_at, updated_at, activated_at"
    )

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        return self._clock.now_iso() if self._clock is not None else utc_now_iso()

    def create(
        self,
        uow: UnitOfWork,
        *,
        guardrail_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> GuardrailRecord:
        now = created_at or self._now()
        try:
            uow.connection.execute(
                """
                INSERT INTO guardrails
                    (guardrail_id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guardrail_id, name, description, now, now),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("creating guardrail", exc) from exc
        row = self.get(uow, guardrail_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Guardrail missing immediately after insert.",
                {"guardrail_id": guardrail_id},
            )
        return row

    def get(self, uow: UnitOfWork, guardrail_id: str) -> GuardrailRecord | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._RECORD_COLUMNS} FROM guardrails g "
                "WHERE g.guardrail_id = ?",
                (guardrail_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading guardrail", exc) from exc
        return None if row is None else self._row_to_record(row)

    def get_by_name(self, uow: UnitOfWork, name: str) -> GuardrailRecord | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._RECORD_COLUMNS} FROM guardrails g WHERE g.name = ?",
                (name,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading guardrail by name", exc) from exc
        return None if row is None else self._row_to_record(row)

    def list(self, uow: UnitOfWork) -> list[GuardrailRecord]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._RECORD_COLUMNS} FROM guardrails g "
                "ORDER BY g.created_at, g.guardrail_id"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing guardrails", exc) from exc
        return [self._row_to_record(row) for row in rows]

    def update(
        self,
        uow: UnitOfWork,
        *,
        guardrail_id: str,
        name: str | None = None,
        description: Any = _UNSET,
    ) -> GuardrailRecord | None:
        sets: list[str] = []
        params: list[Any] = []
        if name is not None:
            sets.append("name = ?")
            params.append(name)
        if description != _UNSET:
            sets.append("description = ?")
            params.append(description)
        if not sets:
            return self.get(uow, guardrail_id)
        sets.append("updated_at = ?")
        params.append(self._now())
        params.append(guardrail_id)
        try:
            cur = uow.connection.execute(
                f"UPDATE guardrails SET {', '.join(sets)} WHERE guardrail_id = ?",
                tuple(params),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("updating guardrail", exc) from exc
        if cur.rowcount == 0:
            return None
        return self.get(uow, guardrail_id)

    def delete(self, uow: UnitOfWork, *, guardrail_id: str) -> bool:
        try:
            cur = uow.connection.execute(
                "DELETE FROM guardrails WHERE guardrail_id = ?", (guardrail_id,)
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("deleting guardrail", exc) from exc
        return cur.rowcount > 0

    def add_version(
        self,
        uow: UnitOfWork,
        *,
        guardrail_id: str,
        status: str,
        evaluator_kind: str,
        evaluator_config: Mapping[str, Any],
        surfaces: Sequence[str],
        field_targets: Sequence[str],
        created_at: str | None = None,
        activated_at: str | None = None,
    ) -> GuardrailVersion:
        fields = validate_guardrail_version_form(
            status=status,
            evaluator_kind=evaluator_kind,
            evaluator_config=evaluator_config,
            surfaces=surfaces,
            field_targets=field_targets,
        )
        now = created_at or self._now()
        active_at = activated_at if fields["status"] == "active" else None
        if fields["status"] == "active" and active_at is None:
            active_at = now
        try:
            row = uow.connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM guardrail_versions "
                "WHERE guardrail_id = ?",
                (guardrail_id,),
            ).fetchone()
            next_version = int(row[0])
            uow.connection.execute(
                """
                INSERT INTO guardrail_versions
                    (guardrail_id, version, status, evaluator_kind,
                     evaluator_config, surfaces, field_targets, created_at,
                     updated_at, activated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guardrail_id,
                    next_version,
                    fields["status"],
                    fields["evaluator_kind"],
                    _dumps(fields["evaluator_config"]),
                    _dumps(list(fields["surfaces"])),
                    _dumps(list(fields["field_targets"])),
                    now,
                    now,
                    active_at,
                ),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("appending guardrail version", exc) from exc
        stored = self.get_version(
            uow, guardrail_id=guardrail_id, version=next_version
        )
        if stored is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Guardrail version missing immediately after insert.",
                {"guardrail_id": guardrail_id, "version": next_version},
            )
        return stored

    def get_version(
        self, uow: UnitOfWork, *, guardrail_id: str, version: int
    ) -> GuardrailVersion | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._VERSION_COLUMNS} FROM guardrail_versions "
                "WHERE guardrail_id = ? AND version = ?",
                (guardrail_id, version),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading guardrail version", exc) from exc
        return None if row is None else self._row_to_version(row)

    def latest_active_version(
        self, uow: UnitOfWork, *, guardrail_id: str
    ) -> GuardrailVersion | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._VERSION_COLUMNS} FROM guardrail_versions "
                "WHERE guardrail_id = ? AND status = 'active' "
                "ORDER BY version DESC LIMIT 1",
                (guardrail_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "reading latest active guardrail version", exc
            ) from exc
        return None if row is None else self._row_to_version(row)

    def list_versions(
        self, uow: UnitOfWork, *, guardrail_id: str
    ) -> list[GuardrailVersion]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._VERSION_COLUMNS} FROM guardrail_versions "
                "WHERE guardrail_id = ? ORDER BY version ASC",
                (guardrail_id,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing guardrail versions", exc) from exc
        return [self._row_to_version(row) for row in rows]

    def versions_for(
        self, uow: UnitOfWork, *, guardrail_ids: Sequence[str]
    ) -> dict[str, list[GuardrailVersion]]:
        ids = [gid for gid in dict.fromkeys(guardrail_ids)]
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        try:
            cur = uow.connection.execute(
                f"SELECT {self._VERSION_COLUMNS} FROM guardrail_versions "
                f"WHERE guardrail_id IN ({placeholders}) "
                "ORDER BY guardrail_id, version ASC",
                tuple(ids),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("bulk-reading guardrail versions", exc) from exc
        out: dict[str, list[GuardrailVersion]] = {}
        for row in rows:
            out.setdefault(row["guardrail_id"], []).append(self._row_to_version(row))
        return out

    def update_version_status(
        self,
        uow: UnitOfWork,
        *,
        guardrail_id: str,
        version: int,
        status: str,
    ) -> GuardrailVersion | None:
        normalised_status = str(status or "").strip().lower()
        if normalised_status not in VERSION_STATUSES:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"status must be one of {sorted(VERSION_STATUSES)}.",
                {"status": status, "supported": sorted(VERSION_STATUSES)},
            )
        now = self._now()
        sets = ["status = ?", "updated_at = ?"]
        params: list[Any] = [normalised_status, now]
        if normalised_status == "active":
            sets.append("activated_at = COALESCE(activated_at, ?)")
            params.append(now)
        params.extend([guardrail_id, version])
        try:
            cur = uow.connection.execute(
                f"UPDATE guardrail_versions SET {', '.join(sets)} "
                "WHERE guardrail_id = ? AND version = ?",
                tuple(params),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "updating guardrail version status", exc
            ) from exc
        if cur.rowcount == 0:
            return None
        return self.get_version(uow, guardrail_id=guardrail_id, version=version)

    @staticmethod
    def _row_to_record(row: Any) -> GuardrailRecord:
        latest_active = row["latest_active_version"]
        return GuardrailRecord(
            guardrail_id=row["guardrail_id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            latest_version=int(row["latest_version"]),
            latest_active_version=None if latest_active is None else int(latest_active),
        )

    @staticmethod
    def _row_to_version(row: Any) -> GuardrailVersion:
        return GuardrailVersion(
            guardrail_id=row["guardrail_id"],
            version=int(row["version"]),
            status=row["status"],
            evaluator_kind=row["evaluator_kind"],
            evaluator_config=_loads_dict(row["evaluator_config"]),
            surfaces=_loads_tuple(row["surfaces"]),
            field_targets=_loads_tuple(row["field_targets"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            activated_at=row["activated_at"],
        )


class SqliteGuardrailAssignmentRepo:
    """Persistence and effective resolution for guardrail assignments."""

    _COLUMNS = (
        "assignment_id, scope_kind, group_id, guardrail_id, version_mode, "
        "pinned_version, mode, priority, enabled, created_at, updated_at"
    )

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock = clock

    def _now(self) -> str:
        return self._clock.now_iso() if self._clock is not None else utc_now_iso()

    def create(
        self,
        uow: UnitOfWork,
        *,
        assignment_id: str,
        scope_kind: str,
        group_id: str | None,
        guardrail_id: str,
        version_mode: str = "latest",
        pinned_version: int | None = None,
        mode: str = "enforce",
        priority: int = 100,
        enabled: bool = True,
        created_at: str | None = None,
    ) -> GuardrailAssignment:
        fields = validate_guardrail_assignment_form(
            scope_kind=scope_kind,
            group_id=group_id,
            guardrail_id=guardrail_id,
            version_mode=version_mode,
            pinned_version=pinned_version,
            mode=mode,
            priority=priority,
            enabled=enabled,
        )
        self._ensure_pinned_active(
            uow,
            guardrail_id=fields["guardrail_id"],
            version_mode=fields["version_mode"],
            pinned_version=fields["pinned_version"],
        )
        now = created_at or self._now()
        try:
            uow.connection.execute(
                f"""
                INSERT INTO guardrail_assignments ({self._COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assignment_id,
                    fields["scope_kind"],
                    fields["group_id"],
                    fields["guardrail_id"],
                    fields["version_mode"],
                    fields["pinned_version"],
                    fields["mode"],
                    fields["priority"],
                    1 if fields["enabled"] else 0,
                    now,
                    now,
                ),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("creating guardrail assignment", exc) from exc
        row = self.get(uow, assignment_id)
        if row is None:  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.DB_ERROR,
                "Guardrail assignment missing immediately after insert.",
                {"assignment_id": assignment_id},
            )
        return row

    def get(
        self, uow: UnitOfWork, assignment_id: str
    ) -> GuardrailAssignment | None:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM guardrail_assignments "
                "WHERE assignment_id = ?",
                (assignment_id,),
            )
            row = cur.fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception("reading guardrail assignment", exc) from exc
        return None if row is None else self._row_to_assignment(row)

    def list(self, uow: UnitOfWork) -> list[GuardrailAssignment]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM guardrail_assignments "
                "ORDER BY priority, assignment_id"
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception("listing guardrail assignments", exc) from exc
        return [self._row_to_assignment(row) for row in rows]

    def list_for_group(
        self, uow: UnitOfWork, *, group_id: str
    ) -> list[GuardrailAssignment]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM guardrail_assignments "
                "WHERE group_id = ? ORDER BY priority, assignment_id",
                (group_id,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "listing group guardrail assignments", exc
            ) from exc
        return [self._row_to_assignment(row) for row in rows]

    def list_for_guardrail(
        self, uow: UnitOfWork, *, guardrail_id: str
    ) -> list[GuardrailAssignment]:
        try:
            cur = uow.connection.execute(
                f"SELECT {self._COLUMNS} FROM guardrail_assignments "
                "WHERE guardrail_id = ? ORDER BY priority, assignment_id",
                (guardrail_id,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "listing guardrail reverse assignments", exc
            ) from exc
        return [self._row_to_assignment(row) for row in rows]

    def list_for_agent(
        self, uow: UnitOfWork, *, agent_id: str
    ) -> list[GuardrailAssignment]:
        try:
            cur = uow.connection.execute(
                f"""
                SELECT {self._COLUMNS}
                FROM guardrail_assignments
                WHERE scope_kind = 'global'
                UNION ALL
                SELECT a.{self._COLUMNS.replace(', ', ', a.')}
                FROM guardrail_assignments a
                JOIN agent_group_members m ON m.group_id = a.group_id
                WHERE a.scope_kind = 'agent_group' AND m.agent_id = ?
                ORDER BY priority, guardrail_id, assignment_id
                """,
                (agent_id,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "listing agent effective guardrail assignments", exc
            ) from exc
        return [self._row_to_assignment(row) for row in rows]

    def effective_for_agent(
        self, uow: UnitOfWork, *, agent_id: str
    ) -> list[EffectiveGuardrail]:
        assignments = self.list_for_agent(uow, agent_id=agent_id)
        guardrail_ids = [assignment.guardrail_id for assignment in assignments]
        versions_by_guardrail = self._versions_for(uow, guardrail_ids=guardrail_ids)
        return resolve_effective_guardrails(assignments, versions_by_guardrail)

    def update(
        self,
        uow: UnitOfWork,
        *,
        assignment_id: str,
        mode: str | None = None,
        priority: int | None = None,
        enabled: bool | None = None,
    ) -> GuardrailAssignment | None:
        sets: list[str] = []
        params: list[Any] = []
        if mode is not None:
            fields = validate_guardrail_assignment_form(
                scope_kind="global",
                guardrail_id="placeholder",
                mode=mode,
            )
            sets.append("mode = ?")
            params.append(fields["mode"])
        if priority is not None:
            fields = validate_guardrail_assignment_form(
                scope_kind="global",
                guardrail_id="placeholder",
                priority=priority,
            )
            sets.append("priority = ?")
            params.append(fields["priority"])
        if enabled is not None:
            if not isinstance(enabled, bool):
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "enabled must be a boolean.",
                    {"enabled": enabled, "type": type(enabled).__name__},
                )
            sets.append("enabled = ?")
            params.append(1 if enabled else 0)
        if not sets:
            return self.get(uow, assignment_id)
        sets.append("updated_at = ?")
        params.append(self._now())
        params.append(assignment_id)
        try:
            cur = uow.connection.execute(
                f"UPDATE guardrail_assignments SET {', '.join(sets)} "
                "WHERE assignment_id = ?",
                tuple(params),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("updating guardrail assignment", exc) from exc
        if cur.rowcount == 0:
            return None
        return self.get(uow, assignment_id)

    def delete(self, uow: UnitOfWork, *, assignment_id: str) -> bool:
        try:
            cur = uow.connection.execute(
                "DELETE FROM guardrail_assignments WHERE assignment_id = ?",
                (assignment_id,),
            )
        except sqlite3.Error as exc:
            raise db_error_from_exception("deleting guardrail assignment", exc) from exc
        return cur.rowcount > 0

    def _ensure_pinned_active(
        self,
        uow: UnitOfWork,
        *,
        guardrail_id: str,
        version_mode: str,
        pinned_version: int | None,
    ) -> None:
        if version_mode != "pinned":
            return
        try:
            row = uow.connection.execute(
                "SELECT status FROM guardrail_versions "
                "WHERE guardrail_id = ? AND version = ?",
                (guardrail_id, pinned_version),
            ).fetchone()
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "validating pinned guardrail assignment", exc
            ) from exc
        if row is None or row["status"] != "active":
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "pinned guardrail assignments require an active version.",
                {
                    "guardrail_id": guardrail_id,
                    "pinned_version": pinned_version,
                    "resolution_status": RESOLUTION_CONFIG_UNAVAILABLE,
                },
            )

    def _versions_for(
        self, uow: UnitOfWork, *, guardrail_ids: Sequence[str]
    ) -> dict[str, list[GuardrailVersion]]:
        ids = [gid for gid in dict.fromkeys(guardrail_ids)]
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        try:
            cur = uow.connection.execute(
                "SELECT guardrail_id, version, status, evaluator_kind, "
                "evaluator_config, surfaces, field_targets, created_at, "
                "updated_at, activated_at FROM guardrail_versions "
                f"WHERE guardrail_id IN ({placeholders}) "
                "ORDER BY guardrail_id, version ASC",
                tuple(ids),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise db_error_from_exception(
                "reading guardrail versions for assignments", exc
            ) from exc
        out: dict[str, list[GuardrailVersion]] = {}
        for row in rows:
            out.setdefault(row["guardrail_id"], []).append(
                SqliteGuardrailRepo._row_to_version(row)
            )
        return out

    @staticmethod
    def _row_to_assignment(row: Any) -> GuardrailAssignment:
        return GuardrailAssignment(
            assignment_id=row["assignment_id"],
            scope_kind=row["scope_kind"],
            group_id=row["group_id"],
            guardrail_id=row["guardrail_id"],
            version_mode=row["version_mode"],
            pinned_version=row["pinned_version"],
            mode=row["mode"],
            priority=int(row["priority"]),
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
