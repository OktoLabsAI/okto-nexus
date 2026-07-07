"""MCP tools for operator guardrail administration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import Field

from okto_nexus.application.guardrail_admin import GuardrailAdminService
from okto_nexus.domain.approvals import OPERATOR_AGENT_ID
from okto_nexus.domain.ids import resolve_workspace_id
from okto_nexus.envelope import require_json_object_param, tool_envelope
from okto_nexus.errors import ErrorCode, OktoNexusError

from ...http.identity_ctx import get_authenticated_agent

_P_OP = "Operation name."
_P_BODY = "JSON object payload."
_P_ID = "Resource id."
_P_AGENT = "Agent id."
_P_ROOT = "Project root; workspace_id = sha256(realpath)."
_P_AFTER = "Return denial events with event_id > after."
_P_LIMIT = "Max denial events."


def build_service(deps: Any) -> GuardrailAdminService:
    return GuardrailAdminService(
        connection_factory=deps.connection_factory,
        groups=deps.repos.agent_groups,
        guardrails=deps.repos.guardrails,
        assignments=deps.repos.guardrail_assignments,
        agents=deps.repos.agents,
        events=deps.repos.events,
        max_denial_limit=deps.config.max_event_limit,
    )


def _require_operator_agent() -> None:
    caller = get_authenticated_agent()
    if caller is None:
        return
    if caller.agent_id != OPERATOR_AGENT_ID:
        raise OktoNexusError(
            ErrorCode.PERMISSION_DENIED,
            "This guardrail administration tool is operator-only.",
            {"agent_id": caller.agent_id, "required": OPERATOR_AGENT_ID},
        )


def _body(value: Any) -> Mapping[str, Any]:
    checked = require_json_object_param("body", value, required=False, example="{}")
    if checked is None:
        return {}
    if not isinstance(checked, Mapping):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "body must be a JSON object.",
            {"body_type": type(checked).__name__},
        )
    return checked


def _op(value: str) -> str:
    return str(value or "").strip().lower()


def register(server: Any, deps: Any) -> None:
    service = build_service(deps)

    @server.tool()
    @tool_envelope
    def guardrail_group_manage(
        operation: Annotated[str, Field(description=_P_OP)],
        group_id: Annotated[str | None, Field(description=_P_ID)] = None,
        agent_id: Annotated[str | None, Field(description=_P_AGENT)] = None,
        body: Annotated[Any, Field(description=_P_BODY)] = None,
    ) -> dict[str, Any]:
        """Operator-only group CRUD and membership operations."""
        _require_operator_agent()
        op = _op(operation)
        payload = _body(body)
        if op == "create":
            return service.create_group(
                name=payload.get("name"), description=payload.get("description")
            )
        if op == "list":
            return {"items": service.list_groups()}
        if op == "get":
            return service.get_group(group_id=group_id)
        if op == "update":
            return service.update_group(group_id=group_id, patch=payload)
        if op == "delete":
            return service.delete_group(group_id=group_id)
        if op == "add_member":
            return service.add_group_member(
                group_id=group_id, agent_id=payload.get("agent_id", agent_id)
            )
        if op == "remove_member":
            return service.remove_group_member(group_id=group_id, agent_id=agent_id)
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "operation must be create, list, get, update, delete, add_member or remove_member.",
            {"operation": operation},
        )

    @server.tool()
    @tool_envelope
    def guardrail_manage(
        operation: Annotated[str, Field(description=_P_OP)],
        guardrail_id: Annotated[str | None, Field(description=_P_ID)] = None,
        body: Annotated[Any, Field(description=_P_BODY)] = None,
    ) -> dict[str, Any]:
        """Operator-only guardrail header CRUD."""
        _require_operator_agent()
        op = _op(operation)
        payload = _body(body)
        if op == "create":
            return service.create_guardrail(
                name=payload.get("name"), description=payload.get("description")
            )
        if op == "list":
            return {"items": service.list_guardrails()}
        if op == "get":
            return service.get_guardrail(guardrail_id=guardrail_id)
        if op == "update":
            return service.update_guardrail(guardrail_id=guardrail_id, patch=payload)
        if op == "delete":
            return service.delete_guardrail(guardrail_id=guardrail_id)
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "operation must be create, list, get, update or delete.",
            {"operation": operation},
        )

    @server.tool()
    @tool_envelope
    def guardrail_version_manage(
        operation: Annotated[str, Field(description=_P_OP)],
        guardrail_id: Annotated[str, Field(description=_P_ID)],
        version: Annotated[int | None, Field(description=_P_ID)] = None,
        body: Annotated[Any, Field(description=_P_BODY)] = None,
    ) -> dict[str, Any]:
        """Operator-only guardrail version operations."""
        _require_operator_agent()
        op = _op(operation)
        payload = _body(body)
        if op == "add":
            return service.add_version(
                guardrail_id=guardrail_id,
                status=payload.get("status", "draft"),
                evaluator_kind=payload.get("evaluator_kind"),
                evaluator_config=payload.get("evaluator_config"),
                surfaces=payload.get("surfaces"),
                field_targets=payload.get("field_targets"),
            )
        if op == "list":
            return {"items": service.list_versions(guardrail_id=guardrail_id)}
        if op == "update_status":
            return service.update_version_status(
                guardrail_id=guardrail_id,
                version=version,
                status=payload.get("status"),
            )
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "operation must be add, list or update_status.",
            {"operation": operation},
        )

    @server.tool()
    @tool_envelope
    def guardrail_assignment_manage(
        operation: Annotated[str, Field(description=_P_OP)],
        assignment_id: Annotated[str | None, Field(description=_P_ID)] = None,
        group_id: Annotated[str | None, Field(description=_P_ID)] = None,
        guardrail_id: Annotated[str | None, Field(description=_P_ID)] = None,
        agent_id: Annotated[str | None, Field(description=_P_AGENT)] = None,
        body: Annotated[Any, Field(description=_P_BODY)] = None,
    ) -> dict[str, Any]:
        """Operator-only guardrail assignment operations."""
        _require_operator_agent()
        op = _op(operation)
        payload = _body(body)
        if op == "create":
            return service.create_assignment(
                scope_kind=payload.get("scope_kind"),
                group_id=payload.get("group_id"),
                guardrail_id=payload.get("guardrail_id"),
                version_mode=payload.get("version_mode", "latest"),
                pinned_version=payload.get("pinned_version"),
                mode=payload.get("mode", "enforce"),
                priority=payload.get("priority", 100),
                enabled=payload.get("enabled", True),
            )
        if op == "list":
            return {
                "items": service.list_assignments(
                    group_id=group_id,
                    guardrail_id=guardrail_id,
                    agent_id=agent_id,
                )
            }
        if op == "update":
            return service.update_assignment(assignment_id=assignment_id, patch=payload)
        if op == "delete":
            return service.delete_assignment(assignment_id=assignment_id)
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "operation must be create, list, update or delete.",
            {"operation": operation},
        )

    @server.tool()
    @tool_envelope
    def guardrail_denial_list(
        project_root: Annotated[str, Field(description=_P_ROOT)],
        after: Annotated[int, Field(description=_P_AFTER)] = 0,
        limit: Annotated[int, Field(description=_P_LIMIT)] = 100,
    ) -> dict[str, Any]:
        """Operator-only scrubbed guardrail.denied events."""
        _require_operator_agent()
        return service.list_denials(
            workspace_id=resolve_workspace_id(project_root),
            cursor=after,
            limit=limit,
        )
