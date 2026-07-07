"""Operator use cases for guardrails, agent groups and scrubbed denials.

This is the administrative surface for the guardrail tables introduced by
migration 025. Runtime enforcement lives in :mod:`okto_nexus.application.guardrails`;
this service deliberately does not evaluate content nor alter write-path
guarding. It stages guardrail headers/versions, group rosters and assignments,
and exposes a scrubbed denial read model for operator dashboards and tools.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..domain.base import new_id
from ..domain.guardrails import (
    AgentGroupMember,
    AgentGroupRecord,
    GuardrailAssignment,
    GuardrailRecord,
    GuardrailVersion,
    validate_group_header_form,
    validate_guardrail_assignment_form,
    validate_guardrail_header_form,
    validate_guardrail_version_form,
)
from ..errors import ErrorCode, OktoNexusError
from .guardrails import GUARDRAIL_DENIED_EVENT, GUARDRAIL_STREAM
from .ports import (
    AgentGroupRepo,
    AgentRepo,
    ConnectionFactory,
    EventRepo,
    GuardrailAssignmentRepo,
    GuardrailRepo,
    UnitOfWork,
)

_UNSET = object()
_DENIAL_FORBIDDEN_KEYS = frozenset(
    {
        "subject",
        "body",
        "payload",
        "content",
        "acceptance_criteria",
        "excerpt",
        "excerpts",
        "keyword",
        "keywords",
        "capture",
        "captures",
        "pii",
    }
)


def _group(
    record: AgentGroupRecord, members: list[AgentGroupMember] | None = None
) -> dict[str, Any]:
    data = {
        "group_id": record.group_id,
        "name": record.name,
        "description": record.description,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
    if members is not None:
        data["members"] = [_member(member) for member in members]
    return data


def _member(record: AgentGroupMember) -> dict[str, Any]:
    return {
        "group_id": record.group_id,
        "agent_id": record.agent_id,
        "created_at": record.created_at,
    }


def _guardrail(
    record: GuardrailRecord, versions: list[GuardrailVersion] | None = None
) -> dict[str, Any]:
    data = {
        "guardrail_id": record.guardrail_id,
        "name": record.name,
        "description": record.description,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "latest_version": record.latest_version,
        "latest_active_version": record.latest_active_version,
    }
    if versions is not None:
        data["versions"] = [_version(version) for version in versions]
    return data


def _version(record: GuardrailVersion) -> dict[str, Any]:
    return {
        "guardrail_id": record.guardrail_id,
        "version": record.version,
        "status": record.status,
        "evaluator_kind": record.evaluator_kind,
        "evaluator_config": dict(record.evaluator_config),
        "surfaces": list(record.surfaces),
        "field_targets": list(record.field_targets),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "activated_at": record.activated_at,
    }


def _assignment(record: GuardrailAssignment) -> dict[str, Any]:
    return {
        "assignment_id": record.assignment_id,
        "scope_kind": record.scope_kind,
        "group_id": record.group_id,
        "guardrail_id": record.guardrail_id,
        "version_mode": record.version_mode,
        "pinned_version": record.pinned_version,
        "mode": record.mode,
        "priority": record.priority,
        "enabled": record.enabled,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _clean_text(value: Any, *, field: str, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} is required.",
                {field: value},
            )
        return None
    if not isinstance(value, str):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{field} must be a string.",
            {field: value, "type": type(value).__name__},
        )
    text = value.strip()
    if required and not text:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{field} is required.",
            {field: value},
        )
    return text or None


def _patch_value(patch: Mapping[str, Any], field: str, current: Any) -> Any:
    return patch[field] if field in patch else current


def _scrub_denial_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in _DENIAL_FORBIDDEN_KEYS:
                continue
            scrubbed[key_text] = _scrub_denial_payload(item)
        return scrubbed
    if isinstance(value, list):
        return [_scrub_denial_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_scrub_denial_payload(item) for item in value]
    return value


class GuardrailAdminService:
    """Operator CRUD for guardrails/groups plus scrubbed denial reads."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        groups: AgentGroupRepo,
        guardrails: GuardrailRepo,
        assignments: GuardrailAssignmentRepo,
        agents: AgentRepo,
        events: EventRepo,
        max_denial_limit: int = 1000,
    ) -> None:
        self._cf = connection_factory
        self._groups = groups
        self._guardrails = guardrails
        self._assignments = assignments
        self._agents = agents
        self._events = events
        self._max_denial_limit = int(max_denial_limit)

    # ------------------------------------------------------------------ #
    # Groups
    # ------------------------------------------------------------------ #
    def create_group(self, *, name: Any, description: Any = None) -> dict[str, Any]:
        fields = validate_group_header_form(name=name, description=description)
        with self._cf.unit_of_work() as uow:
            self._reject_duplicate_group_name(uow, name=fields["name"], excluding=None)
            record = self._groups.create(
                uow,
                group_id=new_id("grp"),
                name=fields["name"],
                description=fields["description"],
            )
        return _group(record, [])

    def list_groups(self) -> list[dict[str, Any]]:
        with self._cf.unit_of_work(write=False) as uow:
            return [
                _group(record, self._groups.list_members(uow, group_id=record.group_id))
                for record in self._groups.list(uow)
            ]

    def get_group(self, *, group_id: Any) -> dict[str, Any]:
        gid = self._id(group_id, field="group_id")
        with self._cf.unit_of_work(write=False) as uow:
            record = self._require_group(uow, group_id=gid)
            members = self._groups.list_members(uow, group_id=gid)
        return _group(record, members)

    def update_group(
        self, *, group_id: Any, patch: Mapping[str, Any]
    ) -> dict[str, Any]:
        gid = self._id(group_id, field="group_id")
        with self._cf.unit_of_work() as uow:
            existing = self._require_group(uow, group_id=gid)
            fields = validate_group_header_form(
                name=_patch_value(patch, "name", existing.name),
                description=_patch_value(patch, "description", existing.description),
            )
            self._reject_duplicate_group_name(uow, name=fields["name"], excluding=gid)
            record = self._groups.update(
                uow,
                group_id=gid,
                name=fields["name"],
                description=fields["description"],
            )
            if record is None:  # pragma: no cover - _require_group guards it
                record = self._require_group(uow, group_id=gid)
            members = self._groups.list_members(uow, group_id=gid)
        return _group(record, members)

    def delete_group(self, *, group_id: Any) -> dict[str, Any]:
        gid = self._id(group_id, field="group_id")
        with self._cf.unit_of_work() as uow:
            self._require_group(uow, group_id=gid)
            in_use = self._assignments.list_for_group(uow, group_id=gid)
            if in_use:
                raise OktoNexusError(
                    ErrorCode.CONFLICT,
                    f"Agent group {gid!r} has guardrail assignment(s) and cannot be deleted.",
                    {
                        "resource": "agent_group",
                        "group_id": gid,
                        "assignments": [item.assignment_id for item in in_use],
                        "total_assignments": len(in_use),
                    },
                )
            self._groups.delete(uow, group_id=gid)
        return {"deleted": True, "group_id": gid}

    def add_group_member(self, *, group_id: Any, agent_id: Any) -> dict[str, Any]:
        gid = self._id(group_id, field="group_id")
        aid = self._id(agent_id, field="agent_id")
        with self._cf.unit_of_work() as uow:
            self._require_group(uow, group_id=gid)
            if self._agents.get(uow, aid) is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"Agent {aid!r} is not registered.",
                    {"agent_id": aid},
                )
            record = self._groups.add_member(uow, group_id=gid, agent_id=aid)
        return _member(record)

    def remove_group_member(self, *, group_id: Any, agent_id: Any) -> dict[str, Any]:
        gid = self._id(group_id, field="group_id")
        aid = self._id(agent_id, field="agent_id")
        with self._cf.unit_of_work() as uow:
            self._require_group(uow, group_id=gid)
            if not self._groups.remove_member(uow, group_id=gid, agent_id=aid):
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"Agent {aid!r} is not a member of group {gid!r}.",
                    {"group_id": gid, "agent_id": aid},
                )
        return {"deleted": True, "group_id": gid, "agent_id": aid}

    # ------------------------------------------------------------------ #
    # Guardrails and versions
    # ------------------------------------------------------------------ #
    def create_guardrail(self, *, name: Any, description: Any = None) -> dict[str, Any]:
        fields = validate_guardrail_header_form(name=name, description=description)
        with self._cf.unit_of_work() as uow:
            self._reject_duplicate_guardrail_name(
                uow, name=fields["name"], excluding=None
            )
            record = self._guardrails.create(
                uow,
                guardrail_id=new_id("grd"),
                name=fields["name"],
                description=fields["description"],
            )
        return _guardrail(record, [])

    def list_guardrails(self) -> list[dict[str, Any]]:
        with self._cf.unit_of_work(write=False) as uow:
            return [_guardrail(record) for record in self._guardrails.list(uow)]

    def get_guardrail(self, *, guardrail_id: Any) -> dict[str, Any]:
        gid = self._id(guardrail_id, field="guardrail_id")
        with self._cf.unit_of_work(write=False) as uow:
            record = self._require_guardrail(uow, guardrail_id=gid)
            versions = self._guardrails.list_versions(uow, guardrail_id=gid)
        return _guardrail(record, versions)

    def update_guardrail(
        self, *, guardrail_id: Any, patch: Mapping[str, Any]
    ) -> dict[str, Any]:
        gid = self._id(guardrail_id, field="guardrail_id")
        with self._cf.unit_of_work() as uow:
            existing = self._require_guardrail(uow, guardrail_id=gid)
            fields = validate_guardrail_header_form(
                name=_patch_value(patch, "name", existing.name),
                description=_patch_value(patch, "description", existing.description),
            )
            self._reject_duplicate_guardrail_name(
                uow, name=fields["name"], excluding=gid
            )
            record = self._guardrails.update(
                uow,
                guardrail_id=gid,
                name=fields["name"],
                description=fields["description"],
            )
            if record is None:  # pragma: no cover - _require_guardrail guards it
                record = self._require_guardrail(uow, guardrail_id=gid)
            versions = self._guardrails.list_versions(uow, guardrail_id=gid)
        return _guardrail(record, versions)

    def delete_guardrail(self, *, guardrail_id: Any) -> dict[str, Any]:
        gid = self._id(guardrail_id, field="guardrail_id")
        with self._cf.unit_of_work() as uow:
            self._require_guardrail(uow, guardrail_id=gid)
            in_use = self._assignments.list_for_guardrail(uow, guardrail_id=gid)
            if in_use:
                raise OktoNexusError(
                    ErrorCode.CONFLICT,
                    f"Guardrail {gid!r} has assignment(s) and cannot be deleted.",
                    {
                        "resource": "guardrail",
                        "guardrail_id": gid,
                        "assignments": [item.assignment_id for item in in_use],
                        "total_assignments": len(in_use),
                    },
                )
            self._guardrails.delete(uow, guardrail_id=gid)
        return {"deleted": True, "guardrail_id": gid}

    def add_version(
        self,
        *,
        guardrail_id: Any,
        status: Any = "draft",
        evaluator_kind: Any = None,
        evaluator_config: Any = None,
        surfaces: Any = None,
        field_targets: Any = None,
    ) -> dict[str, Any]:
        gid = self._id(guardrail_id, field="guardrail_id")
        fields = validate_guardrail_version_form(
            status=status,
            evaluator_kind=evaluator_kind,
            evaluator_config=evaluator_config,
            surfaces=surfaces,
            field_targets=field_targets,
        )
        with self._cf.unit_of_work() as uow:
            self._require_guardrail(uow, guardrail_id=gid)
            record = self._guardrails.add_version(
                uow,
                guardrail_id=gid,
                status=fields["status"],
                evaluator_kind=fields["evaluator_kind"],
                evaluator_config=fields["evaluator_config"],
                surfaces=fields["surfaces"],
                field_targets=fields["field_targets"],
            )
        return _version(record)

    def list_versions(self, *, guardrail_id: Any) -> list[dict[str, Any]]:
        gid = self._id(guardrail_id, field="guardrail_id")
        with self._cf.unit_of_work(write=False) as uow:
            self._require_guardrail(uow, guardrail_id=gid)
            return [
                _version(record)
                for record in self._guardrails.list_versions(uow, guardrail_id=gid)
            ]

    def update_version_status(
        self, *, guardrail_id: Any, version: Any, status: Any
    ) -> dict[str, Any]:
        gid = self._id(guardrail_id, field="guardrail_id")
        ver = self._positive_int(version, field="version")
        with self._cf.unit_of_work() as uow:
            self._require_guardrail(uow, guardrail_id=gid)
            record = self._guardrails.update_version_status(
                uow, guardrail_id=gid, version=ver, status=status
            )
            if record is None:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"Guardrail version {gid!r}@{ver} was not found.",
                    {"guardrail_id": gid, "version": ver},
                )
        return _version(record)

    # ------------------------------------------------------------------ #
    # Assignments
    # ------------------------------------------------------------------ #
    def create_assignment(
        self,
        *,
        scope_kind: Any,
        group_id: Any = None,
        guardrail_id: Any,
        version_mode: Any = "latest",
        pinned_version: Any = None,
        mode: Any = "enforce",
        priority: Any = 100,
        enabled: Any = True,
    ) -> dict[str, Any]:
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
        with self._cf.unit_of_work() as uow:
            self._require_guardrail(uow, guardrail_id=fields["guardrail_id"])
            if fields["group_id"] is not None:
                self._require_group(uow, group_id=fields["group_id"])
            record = self._assignments.create(
                uow,
                assignment_id=new_id("gra"),
                scope_kind=fields["scope_kind"],
                group_id=fields["group_id"],
                guardrail_id=fields["guardrail_id"],
                version_mode=fields["version_mode"],
                pinned_version=fields["pinned_version"],
                mode=fields["mode"],
                priority=fields["priority"],
                enabled=fields["enabled"],
            )
        return _assignment(record)

    def list_assignments(
        self,
        *,
        group_id: Any = None,
        guardrail_id: Any = None,
        agent_id: Any = None,
    ) -> list[dict[str, Any]]:
        with self._cf.unit_of_work(write=False) as uow:
            if group_id is not None:
                rows = self._assignments.list_for_group(
                    uow, group_id=self._id(group_id, field="group_id")
                )
            elif guardrail_id is not None:
                rows = self._assignments.list_for_guardrail(
                    uow, guardrail_id=self._id(guardrail_id, field="guardrail_id")
                )
            elif agent_id is not None:
                rows = self._assignments.list_for_agent(
                    uow, agent_id=self._id(agent_id, field="agent_id")
                )
            else:
                rows = self._assignments.list(uow)
        return [_assignment(record) for record in rows]

    def update_assignment(
        self, *, assignment_id: Any, patch: Mapping[str, Any]
    ) -> dict[str, Any]:
        aid = self._id(assignment_id, field="assignment_id")
        with self._cf.unit_of_work() as uow:
            self._require_assignment(uow, assignment_id=aid)
            record = self._assignments.update(
                uow,
                assignment_id=aid,
                mode=patch.get("mode"),
                priority=patch.get("priority"),
                enabled=patch.get("enabled"),
            )
            if record is None:  # pragma: no cover - _require_assignment guards it
                record = self._require_assignment(uow, assignment_id=aid)
        return _assignment(record)

    def delete_assignment(self, *, assignment_id: Any) -> dict[str, Any]:
        aid = self._id(assignment_id, field="assignment_id")
        with self._cf.unit_of_work() as uow:
            self._require_assignment(uow, assignment_id=aid)
            self._assignments.delete(uow, assignment_id=aid)
        return {"deleted": True, "assignment_id": aid}

    # ------------------------------------------------------------------ #
    # Denials
    # ------------------------------------------------------------------ #
    def list_denials(
        self,
        *,
        workspace_id: Any,
        cursor: Any = 0,
        limit: Any = 100,
    ) -> dict[str, Any]:
        wid = self._id(workspace_id, field="workspace")
        after = max(0, int(cursor or 0))
        page_limit = min(self._max_denial_limit, max(1, int(limit or 100)))
        with self._cf.unit_of_work(write=False) as uow:
            rows = self._events.list_after(
                uow,
                workspace_id=wid,
                stream=GUARDRAIL_STREAM,
                cursor=after,
                limit=page_limit,
                filters={"type": GUARDRAIL_DENIED_EVENT},
            )
        items = [
            {
                "event_id": event.event_id,
                "workspace_id": event.workspace_id,
                "stream": event.stream,
                "type": event.type,
                "actor_agent_id": event.actor_agent_id,
                "created_at": event.created_at,
                "payload": _scrub_denial_payload(event.payload or {}),
            }
            for event in rows
        ]
        return {
            "items": items,
            "next_cursor": items[-1]["event_id"] if items else after,
            "s6_behavior": "audit and warn matches are intentionally silent; only enforce denials emit guardrail.denied events.",
        }

    # ------------------------------------------------------------------ #
    # Internal guards
    # ------------------------------------------------------------------ #
    @staticmethod
    def _id(value: Any, *, field: str) -> str:
        text = _clean_text(value, field=field, required=True)
        assert text is not None
        return text

    @staticmethod
    def _positive_int(value: Any, *, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} must be a positive integer.",
                {field: value},
            )
        return value

    def _require_group(self, uow: UnitOfWork, *, group_id: str) -> AgentGroupRecord:
        record = self._groups.get(uow, group_id)
        if record is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Agent group {group_id!r} was not found.",
                {"group_id": group_id},
            )
        return record

    def _require_guardrail(
        self, uow: UnitOfWork, *, guardrail_id: str
    ) -> GuardrailRecord:
        record = self._guardrails.get(uow, guardrail_id)
        if record is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Guardrail {guardrail_id!r} was not found.",
                {"guardrail_id": guardrail_id},
            )
        return record

    def _require_assignment(
        self, uow: UnitOfWork, *, assignment_id: str
    ) -> GuardrailAssignment:
        record = self._assignments.get(uow, assignment_id)
        if record is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Guardrail assignment {assignment_id!r} was not found.",
                {"assignment_id": assignment_id},
            )
        return record

    def _reject_duplicate_group_name(
        self, uow: UnitOfWork, *, name: str, excluding: str | None
    ) -> None:
        record = self._groups.get_by_name(uow, name)
        if record is not None and record.group_id != excluding:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"Agent group name {name!r} already exists.",
                {"name": name, "group_id": record.group_id},
            )

    def _reject_duplicate_guardrail_name(
        self, uow: UnitOfWork, *, name: str, excluding: str | None
    ) -> None:
        record = self._guardrails.get_by_name(uow, name)
        if record is not None and record.guardrail_id != excluding:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"Guardrail name {name!r} already exists.",
                {"name": name, "guardrail_id": record.guardrail_id},
            )
