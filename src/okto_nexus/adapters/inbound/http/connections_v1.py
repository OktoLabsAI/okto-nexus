"""Direct-object R4 connection protocol endpoint."""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated

from ....domain.permissions import PERMISSION_REGISTRY, PermissionSet
from ....application.execution_binding_proposals import (
    apply_execution_binding, prepare_execution_binding,
)
from ....errors import ErrorCode, OktoNexusError
from ....bootstrap.execution_authority import build_execution_access
from ...outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ...outbound.sqlite.execution_identity import (
    ensure_execution_installation, register_remote_executor,
)
from ...outbound.sqlite.execution_tickets import (
    AUDIENCE, TicketRequestConflict, issue_execution_ticket,
)
from ...outbound.execution.core_inventory import (
    MANAGEMENT_REVISION, protocol_info,
)
from .identity_ctx import get_authenticated_agent, runtime_request_context
from .app import v1_err


_Id = Annotated[str, Field(min_length=1, max_length=160, strict=True)]


class RegisterExecutorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_intent_id: _Id
    connector_id: _Id
    label: Annotated[str, Field(max_length=120, strict=True)]
    control_capabilities: Annotated[list[_Id], Field(max_length=64)]


class BindingTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_intent_id: _Id
    credential_request_id: _Id
    replaces_ticket_id: _Id | None = None
    audience: Annotated[str, Field(strict=True)]
    scopes: Annotated[list[_Id], Field(min_length=1, max_length=8)]
    expires_in: Annotated[int, Field(ge=1, le=600, strict=True)] = 600


class BindingPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_intent_id: _Id
    agent_id_hint: _Id | None = None
    replace_binding_id: _Id | None = None
    adopt_endpoint_id: _Id | None = None
    executor_id: _Id
    adapter_id: _Id
    candidate_ref: Annotated[str, Field(
        pattern=r"^nexus-install-v1:[0-9a-f]{64}$", strict=True)]
    inventory_revision: Annotated[str, Field(
        pattern=r"^sha256:[0-9a-f]{64}$", strict=True)]
    realization_ref: _Id
    workspace_id: _Id
    alias: Annotated[str, Field(min_length=1, max_length=120, strict=True)]


class BindingApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_intent_id: _Id
    proposal_id: _Id
    proposal_revision: Annotated[int, Field(ge=1, strict=True)]
    approved_diff_hash: Annotated[str, Field(
        pattern=r"^sha256:[0-9a-f]{64}$", strict=True)]
    operator_proof_ref: _Id | None = None


_BINDING_TICKET_SCOPES = frozenset({
    "link:connect", "lane:attach", "receipt:publish", "history:read",
    "lease:request",
})


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get('/reach')
    async def reach():
        from ....application.reach import reach_info
        return JSONResponse(reach_info(), headers={'Cache-Control': 'no-store'})

    def binding_error(error, stage):
        status = {ErrorCode.NOT_FOUND: 404, ErrorCode.PERMISSION_DENIED: 403,
                  ErrorCode.CONFLICT: 409, ErrorCode.VALIDATION_ERROR: 422,
                  'RECONCILIATION_REQUIRED': 409}.get(error.code, 500)
        result = v1_err(status, error.code, error.message, stage=stage)
        result.headers["Cache-Control"] = "no-store"
        return result

    @router.get("/connections/protocol")
    async def protocol() -> JSONResponse:
        response = JSONResponse(protocol_info())
        response.headers["X-Nexus-Connections-Revision"] = MANAGEMENT_REVISION
        return response

    @router.get("/connections/me")
    async def me(request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return JSONResponse({"error": {"code": "AUTH_FAILED",
                                        "stage": "authentication",
                                        "message": "Authentication is required.",
                                        "possible_effect": False,
                                        "retry_safe": False,
                                        "operation_id": None, "action": None}},
                                status_code=401)
        hint = request.headers.get("X-Nexus-Agent-Hint")
        if hint and hint != agent.agent_id:
            return JSONResponse({"error": {"code": "SCOPE_MISMATCH",
                                        "stage": "authentication",
                                        "message": "The agent hint does not match the authenticated agent.",
                                        "possible_effect": False,
                                        "retry_safe": False,
                                        "operation_id": None, "action": None}},
                                status_code=403)
        factory = request.app.state.deps.connection_factory
        try:
            server_id, revisions, projection = await anyio.to_thread.run_sync(
                lambda: current_agent_revisions(factory, agent_id=agent.agent_id)
            )
        except OktoNexusError:
            return JSONResponse({"error": {"code": "AUTH_FAILED",
                                        "stage": "authentication",
                                        "message": "The authenticated agent is unavailable.",
                                        "possible_effect": False,
                                        "retry_safe": False,
                                        "operation_id": None, "action": None}},
                                status_code=401)
        permissions = PermissionSet(projection["permissions"])
        allowed = sorted(
            f"{group}.{flag}" for group, values in PERMISSION_REGISTRY.items()
            if group != "limits" for flag in values
            if permissions.allows(group, flag)
        )
        display = projection["metadata"].get("display_name", agent.agent_id)
        if not isinstance(display, str):
            display = agent.agent_id
        return JSONResponse({
            "server_id": server_id, "agent_id": agent.agent_id,
            "display_name": display[:4096], "permissions": allowed,
            "revisions": {
                "authorization": revisions.authorization,
                "configuration": revisions.configuration,
                "credential_epoch": revisions.credential_epoch,
            },
        })

    @router.post("/connections/executors:register")
    async def register_executor(request: Request,
                                body: RegisterExecutorRequest) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return JSONResponse({"error": {"code": "AUTH_FAILED",
                                        "stage": "authentication",
                                        "message": "Authentication is required.",
                                        "possible_effect": False,
                                        "retry_safe": False,
                                        "operation_id": None, "action": None}},
                                status_code=401)
        factory = request.app.state.deps.connection_factory

        def _register():
            registration = register_remote_executor(
                factory, actor_agent_id=agent.agent_id,
                connector_id=body.connector_id,
                client_intent_id=body.client_intent_id, label=body.label,
                # Advertised capabilities are included in the idempotency
                # digest but never authorize an effect by themselves.
                control_capabilities=tuple(body.control_capabilities),
            )
            ticket = issue_execution_ticket(
                factory, server_id=registration.server_id,
                executor_id=registration.executor_id,
                agent_id=agent.agent_id,
            )
            return registration, ticket

        registration, ticket = await anyio.to_thread.run_sync(_register)
        return JSONResponse({
            "server_id": registration.server_id,
            "executor_id": registration.executor_id,
            "connector_id": registration.connector_id,
            "state": "AWAITING_INVENTORY",
            "bootstrap_ticket": ticket.public_dict(),
        }, status_code=200 if registration.reused else 201,
           headers={"Cache-Control": "no-store"})

    @router.post("/connections/bindings:prepare")
    async def prepare_binding(body: BindingPrepareRequest,
                              request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        factory = request.app.state.deps.connection_factory

        def _prepare():
            return prepare_execution_binding(
                factory, actor_agent_id=agent.agent_id,
                approvals=request.app.state.deps.approvals,
                request=body.model_dump(exclude_none=True),
                fresh_publications=request.app.state.inventory_fresh_publications,
                context=runtime_request_context(),
                access=build_execution_access(request.app.state.deps),
            )

        try:
            proposal = await anyio.to_thread.run_sync(_prepare)
        except OktoNexusError as error:
            return binding_error(error, "binding.prepare")
        return JSONResponse(proposal, headers={"Cache-Control": "no-store"})

    @router.post("/connections/bindings:apply")
    async def apply_binding(body: BindingApplyRequest,
                            request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        factory = request.app.state.deps.connection_factory

        def _apply():
            return apply_execution_binding(
                factory, actor_agent_id=agent.agent_id,
                request=body.model_dump(exclude_none=True),
                fresh_publications=request.app.state.inventory_fresh_publications,
                context=runtime_request_context(),
                access=build_execution_access(request.app.state.deps),
            )

        try:
            view = await anyio.to_thread.run_sync(_apply)
        except OktoNexusError as error:
            return binding_error(error, "binding.apply")
        return JSONResponse(view, headers={"Cache-Control": "no-store"})

    @router.get("/connections/bindings/{binding_id}")
    async def binding_view(binding_id: str, request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, 'AUTH_FAILED', 'Authentication is required.')
        if request.query_params:
            return v1_err(422, 'VALIDATION_ERROR', 'Invalid binding query.')
        from ....application.execution_binding_views import read_execution_binding
        deps = request.app.state.deps
        def read():
            server_id = ensure_execution_installation(deps.connection_factory).server_id
            return read_execution_binding(deps.connection_factory, server_id=server_id,
                binding_id=binding_id,
                context=runtime_request_context(),
                access=build_execution_access(deps))
        try:
            view = await anyio.to_thread.run_sync(read)
        except OktoNexusError as error:
            return binding_error(error, 'binding.read')
        return JSONResponse(view, headers={'Cache-Control': 'no-store'})

    @router.post("/connections/bindings/{binding_id}/ticket")
    async def binding_ticket(binding_id: str, body: BindingTicketRequest,
                             request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        scopes = frozenset(body.scopes)
        if (body.audience != AUDIENCE or len(scopes) != len(body.scopes) or
                not scopes <= _BINDING_TICKET_SCOPES):
            return v1_err(400, "VALIDATION_ERROR",
                          "Invalid binding ticket audience or scopes.",
                          stage="validation")
        factory = request.app.state.deps.connection_factory

        def _issue():
            server_id = ensure_execution_installation(factory).server_id
            with factory.unit_of_work(write=False) as uow:
                target = uow.connection.execute(
                    "SELECT b.executor_id FROM execution_bindings b JOIN "
                    "agent_endpoints ep ON ep.endpoint_id=b.endpoint_id WHERE "
                    "b.server_id=? AND b.binding_id=? AND ep.agent_id=?",
                    (server_id, binding_id, agent.agent_id),
                ).fetchone()
            if target is None:
                return None
            return issue_execution_ticket(
                factory, server_id=server_id,
                executor_id=target["executor_id"], agent_id=agent.agent_id,
                binding_id=binding_id, scopes=scopes,
                expires_in=body.expires_in,
                client_intent_id=body.client_intent_id,
                credential_request_id=body.credential_request_id,
                replaces_ticket_id=body.replaces_ticket_id,
            )

        try:
            issued = await anyio.to_thread.run_sync(_issue)
        except TicketRequestConflict as exc:
            return JSONResponse({"error": {
                "code": exc.code, "stage": "credential",
                "message": str(exc), "ticket_id": exc.ticket_id,
                "possible_effect": False, "retry_safe": False,
                "operation_id": None,
                "action": "Request a replacement with a new credential_request_id."
                if exc.code == "CREDENTIAL_MATERIAL_UNAVAILABLE" else None,
            }}, status_code=409, headers={"Cache-Control": "no-store"})
        if issued is None:
            return v1_err(404, "NOT_FOUND",
                          "The binding was not found in this scope.",
                          stage="authorization")
        return JSONResponse(issued.public_dict(),
                            headers={"Cache-Control": "no-store"})

    return router
