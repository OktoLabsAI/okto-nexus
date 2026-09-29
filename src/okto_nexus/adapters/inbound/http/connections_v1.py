"""Direct-object R4 connection protocol endpoint."""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated

from ....domain.permissions import PERMISSION_REGISTRY, PermissionSet
from ....errors import OktoNexusError
from ...outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ...outbound.sqlite.execution_identity import register_remote_executor
from ...outbound.sqlite.execution_tickets import issue_execution_ticket
from ...outbound.execution.core_inventory import (
    MANAGEMENT_REVISION, protocol_info,
)
from .identity_ctx import get_authenticated_agent


_Id = Annotated[str, Field(min_length=1, max_length=160, strict=True)]


class RegisterExecutorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_intent_id: _Id
    connector_id: _Id
    label: Annotated[str, Field(max_length=120, strict=True)]
    control_capabilities: Annotated[list[_Id], Field(max_length=64)]


def build_router() -> APIRouter:
    router = APIRouter()

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

    return router
