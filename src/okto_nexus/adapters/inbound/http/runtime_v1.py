"""Ticket-authenticated R4 technical inventory transport."""

from __future__ import annotations

import anyio
import time
from typing import Annotated
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from nexus_connector_core.protocol import strict_json

from ....application.executor_inventory import publish_executor_inventory
from ....application.execution_realizations import publish_executor_realization
from ....application.execution_intents import (
    read_execution_intent, resolve_execution_intent,
)
from ....application.execution_admission import submit_execution_operation
from ....application.executor_inventory_views import (
    read_executor_inventory, runtime_options_from_inventory,
)
from ....domain.execution.keys import ExecutorKey
from ....errors import ErrorCode, OktoNexusError
from ...outbound.execution.core_inventory import protocol_info
from ...outbound.sqlite.execution_receipts import (
    append_execution_receipt, read_execution_operation_history,
)
from ...outbound.sqlite.execution_identity import ensure_execution_installation
from ...outbound.sqlite.execution_tickets import (
    verify_execution_history_ticket, verify_execution_ticket,
)
from .app import extract_bearer, v1_err
from .identity_ctx import get_authenticated_agent


MAX_INVENTORY_BODY_BYTES = 1024 * 1024
MAX_RECEIPT_BODY_BYTES = 64 * 1024

_Id = Annotated[str, Field(min_length=1, max_length=160, strict=True)]
_Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$", strict=True)]
_CandidateRef = Annotated[str, Field(
    pattern=r"^nexus-install-v1:[0-9a-f]{64}$", strict=True)]


class RealizationPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_intent_id: _Id
    agent_id: _Id
    local_realization_ref: _Id
    realization_revision: Annotated[int, Field(ge=1, strict=True)]
    workspace_id: _Id | None
    workspace_label: Annotated[str, Field(max_length=160, strict=True)]
    adapter_id: _Id
    candidate_ref: _CandidateRef
    inventory_revision: _Digest
    local_root_proof_digest: _Digest
    configuration_digest: _Digest
    local_consent_id: _Id


class ResolveIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_intent_id: _Id
    intent: Annotated[str, Field(strict=True)]
    binding_id: _Id
    workspace_binding_id: _Id
    session_id: _Id | None = None
    new_session: bool | None = None
    text: Annotated[str, Field(max_length=65536, strict=True)] | None = None
    target: dict[str, object] | None = None


class OperationSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_intent_id: _Id
    operation_id: _Id
    resolution_revision: Annotated[int, Field(ge=1, strict=True)]
    intent_hash: _Digest


def build_router() -> APIRouter:
    router = APIRouter()

    @router.put("/runtime/executors/{executor_id}/inventory")
    async def publish_inventory(executor_id: str,
                                request: Request) -> JSONResponse:
        token = extract_bearer(request)
        if token is None:
            return v1_err(401, "AUTH_FAILED",
                          "An execution ticket is required.")
        content_length = request.headers.get("content-length")
        if content_length is not None and (
                not content_length.isdecimal() or
                int(content_length) > MAX_INVENTORY_BODY_BYTES):
            return v1_err(413, "CAPACITY_EXCEEDED",
                          "The inventory body is too large.", stage="validation")
        parts: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_INVENTORY_BODY_BYTES:
                return v1_err(413, "CAPACITY_EXCEEDED",
                              "The inventory body is too large.", stage="validation")
            parts.append(chunk)
        try:
            snapshot = strict_json(b"".join(parts).decode("utf-8", errors="strict"))
        except (UnicodeError, ValueError, RecursionError):
            return v1_err(400, "VALIDATION_ERROR",
                          "The inventory body is invalid JSON.",
                          stage="validation")
        if not isinstance(snapshot, dict):
            return v1_err(400, "VALIDATION_ERROR",
                          "The inventory body must be an object.",
                          stage="validation")
        factory = request.app.state.deps.connection_factory

        def _publish():
            installation = ensure_execution_installation(factory)
            verified = verify_execution_ticket(
                factory, ticket=token, server_id=installation.server_id,
                executor_id=executor_id, scope="inventory:publish",
            )
            return publish_executor_inventory(
                factory, principal=ExecutorKey(installation.server_id,
                                               executor_id),
                producer_instance_id=snapshot.get("producer_instance_id"),
                snapshot=snapshot,
                publication_ticket_id=verified.ticket_id,
            )

        try:
            publication = await anyio.to_thread.run_sync(_publish)
        except OktoNexusError as error:
            status = {ErrorCode.CONFLICT: 409, ErrorCode.PERMISSION_DENIED: 403,
                      ErrorCode.VALIDATION_ERROR: 422}.get(error.code, 500)
            return v1_err(status, error.code, error.message, stage="inventory.publish")
        freshness_key = (publication.server_id, publication.executor_id)
        if not publication.reused:
            request.app.state.inventory_fresh_publications[freshness_key] = (
                publication.publication_sequence, time.monotonic(),
                snapshot["observation_age_ms"],
            )
        receipt = request.app.state.inventory_fresh_publications.get(freshness_key)
        remaining = (max(0, 120_000 - receipt[2] -
                         int((time.monotonic() - receipt[1]) * 1000))
                     if receipt is not None and
                     receipt[0] == publication.publication_sequence else 0)
        return JSONResponse({
            "server_id": publication.server_id,
            "executor_id": publication.executor_id,
            "publication_sequence": publication.publication_sequence,
            "inventory_revision": publication.inventory_revision,
            "fresh_for_ms": remaining,
            "accepted": True,
        }, headers={"Cache-Control": "no-store"})

    @router.get("/runtime/executors/{executor_id}/inventory")
    async def inventory_view(executor_id: str,
                             request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        factory = request.app.state.deps.connection_factory

        def _read():
            server_id = ensure_execution_installation(factory).server_id
            return read_executor_inventory(
                factory, server_id=server_id, executor_id=executor_id,
                agent_id=agent.agent_id,
                fresh_publications=request.app.state.inventory_fresh_publications,
            )

        view = await anyio.to_thread.run_sync(_read)
        return JSONResponse(view, headers={"Cache-Control": "no-store"})

    @router.post("/runtime/executors/{executor_id}/realizations")
    async def publish_realization(executor_id: str,
                                  body: RealizationPublishRequest,
                                  request: Request) -> JSONResponse:
        token = extract_bearer(request)
        if token is None:
            return v1_err(401, "AUTH_FAILED",
                          "An execution ticket is required.")
        factory = request.app.state.deps.connection_factory

        def _publish():
            installation = ensure_execution_installation(factory)
            principal = verify_execution_ticket(
                factory, ticket=token, server_id=installation.server_id,
                executor_id=executor_id, scope="realization:publish",
            )
            return publish_executor_realization(
                factory, principal=principal, request=body.model_dump())

        publication = await anyio.to_thread.run_sync(_publish)
        return JSONResponse(
            publication.public_dict(),
            status_code=200 if publication.reused else 201,
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/runtime/intents:resolve")
    async def resolve_intent(body: ResolveIntentRequest,
                             request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        factory = request.app.state.deps.connection_factory
        resolution = await anyio.to_thread.run_sync(
            lambda: resolve_execution_intent(
                factory, actor_agent_id=agent.agent_id,
                request=body.model_dump(exclude_none=True),
                remote_ready=protocol_info()["remote_execution_ready"],
                fresh_publications=request.app.state.inventory_fresh_publications))
        return JSONResponse(resolution, headers={"Cache-Control": "no-store"})

    @router.get("/runtime/intents/{client_intent_id}")
    async def intent_view(client_intent_id: str,
                          request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        factory = request.app.state.deps.connection_factory
        view = await anyio.to_thread.run_sync(
            lambda: read_execution_intent(
                factory, actor_agent_id=agent.agent_id,
                client_intent_id=client_intent_id))
        return JSONResponse(view, headers={"Cache-Control": "no-store"})

    @router.post("/runtime/operations")
    async def submit_operation(body: OperationSubmitRequest,
                               request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        factory = request.app.state.deps.connection_factory
        view, reused = await anyio.to_thread.run_sync(
            lambda: submit_execution_operation(
                factory, actor_agent_id=agent.agent_id,
                request=body.model_dump(),
                fresh_publications=request.app.state.inventory_fresh_publications,
                remote_ready=protocol_info()["remote_execution_ready"],
            ))
        return JSONResponse(view, status_code=200 if reused else 202,
                            headers={"Cache-Control": "no-store"})

    @router.post("/runtime/operations/{operation_id}/receipts")
    async def publish_operation_receipt(operation_id: str,
                                        request: Request) -> JSONResponse:
        token = extract_bearer(request)
        if token is None:
            return v1_err(401, "AUTH_FAILED",
                          "An execution ticket is required.")
        content_length = request.headers.get("content-length")
        if content_length is not None and (
                not content_length.isdecimal() or
                int(content_length) > MAX_RECEIPT_BODY_BYTES):
            return v1_err(413, "CAPACITY_EXCEEDED",
                          "The receipt body is too large.", stage="validation")
        parts: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_RECEIPT_BODY_BYTES:
                return v1_err(413, "CAPACITY_EXCEEDED",
                              "The receipt body is too large.", stage="validation")
            parts.append(chunk)
        try:
            frame = strict_json(b"".join(parts).decode("utf-8", errors="strict"))
        except (UnicodeError, ValueError, RecursionError):
            return v1_err(400, "VALIDATION_ERROR",
                          "The receipt body is invalid JSON.", stage="validation")
        if not isinstance(frame, dict) or frame.get("operation_id") != operation_id:
            return v1_err(400, "VALIDATION_ERROR",
                          "The receipt operation ID does not match the route.",
                          stage="validation")
        factory = request.app.state.deps.connection_factory

        def _publish():
            installation = ensure_execution_installation(factory)
            principal = verify_execution_ticket(
                factory, ticket=token, server_id=installation.server_id,
                executor_id=frame.get("executor_id"),
                binding_id=frame.get("binding_id"), scope="receipt:publish",
            )
            return append_execution_receipt(
                factory, principal=principal, frame=frame)

        accepted = await anyio.to_thread.run_sync(_publish)
        return JSONResponse({
            "operation_id": accepted.operation_id,
            "receipt_revision": accepted.receipt_revision,
            "stage": accepted.stage, "accepted": True, "reused": accepted.reused,
        }, headers={"Cache-Control": "no-store"})

    @router.get("/runtime/operations/{operation_id}")
    async def operation_view(operation_id: str,
                             request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        token = extract_bearer(request)
        history_ticket = token if token and token.startswith("nxt4_") else None
        if agent is None and history_ticket is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        factory = request.app.state.deps.connection_factory

        def _read():
            server_id = ensure_execution_installation(factory).server_id
            if history_ticket is not None:
                principal = verify_execution_history_ticket(
                    factory, ticket=history_ticket, server_id=server_id,
                    operation_id=operation_id)
                executor_id = principal.executor_id
                subject_agent_id = principal.agent_id
            else:
                executor_id = None
                subject_agent_id = agent.agent_id
            return read_execution_operation_history(
                factory, server_id=server_id, executor_id=executor_id,
                operation_id=operation_id, subject_agent_id=subject_agent_id,
            ).public_view()

        view = await anyio.to_thread.run_sync(_read)
        return JSONResponse(view, headers={"Cache-Control": "no-store"})

    @router.get("/agents/{agent_id}/runtime-options")
    async def runtime_options(agent_id: str, executor_id: str,
                              request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        if agent.agent_id != agent_id:
            return v1_err(403, "SCOPE_MISMATCH",
                          "The requested agent is outside this credential's scope.")
        factory = request.app.state.deps.connection_factory

        def _read():
            server_id = ensure_execution_installation(factory).server_id
            return read_executor_inventory(
                factory, server_id=server_id, executor_id=executor_id,
                agent_id=agent.agent_id,
                fresh_publications=request.app.state.inventory_fresh_publications,
            )

        view = await anyio.to_thread.run_sync(_read)
        return JSONResponse(
            runtime_options_from_inventory(agent_id=agent_id,
                                           inventory_view=view),
            headers={"Cache-Control": "no-store"},
        )

    return router
