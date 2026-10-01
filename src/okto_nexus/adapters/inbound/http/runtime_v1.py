"""Ticket-authenticated R4 technical inventory transport."""

from __future__ import annotations

import anyio
import time
from typing import Annotated, Literal
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
from ....application.execution_capabilities import ExecutionCapabilityService
from ....bootstrap.execution_authority import build_execution_access
from ....domain.runtime_context import RuntimeRequestContext
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


class LocalRealizationPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    client_intent_id: _Id
    agent_id: _Id
    workspace_root: Annotated[str, Field(min_length=1, max_length=4096)]
    workspace_id: _Id | None
    workspace_label: Annotated[str, Field(max_length=160)]
    adapter_id: _Id
    candidate_ref: _CandidateRef
    inventory_revision: _Digest
    local_consent_id: _Id
    approved: bool
    provider_home: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    secret_bindings: dict[str, str] = Field(default_factory=dict, max_length=64)


class ResolveIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_intent_id: _Id
    intent: Annotated[str, Field(strict=True)]
    binding_id: _Id
    workspace_binding_id: _Id
    session_id: _Id | None = None
    new_session: Annotated[bool, Field(strict=True)] | None = None
    text: Annotated[str, Field(max_length=65536, strict=True)] | None = None
    target: dict[str, object] | None = None


class OperationSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_intent_id: _Id
    operation_id: _Id
    resolution_revision: Annotated[int, Field(ge=1, strict=True)]
    intent_hash: _Digest


class NativeApprovalKey(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    server_id: _Id
    executor_id: _Id
    binding_id: _Id
    agent_id: _Id
    workspace_id: _Id
    session_id: _Id
    session_owner_generation: Annotated[int, Field(ge=1)]
    canonical_request_id: _Id
    kind: Literal["native_approval", "native_input"]


class NativeDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    client_intent_id: _Id
    approval_key: NativeApprovalKey
    expected_revision: Annotated[int, Field(ge=1)]
    request_hash: _Digest
    decision: Literal["approve", "deny"]
    cas_token: Annotated[str, Field(min_length=16, max_length=4096)]
    operator_proof_ref: _Id | None = None
    response: dict[str, object] | None = Field(default=None, repr=False)


class CapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_request_id: _Id
    binding_id: _Id
    audience: _Id
    actions: Annotated[list[_Id], Field(max_length=128)]
    replaces_capability_id: _Id | None = None


def build_router() -> APIRouter:
    router = APIRouter()

    def native_error(error):
        status = {"NOT_FOUND": 404, "PERMISSION_DENIED": 403, "APPROVAL_AUTHORITY_REQUIRED": 403,
                  "CONFLICT": 409, "VALIDATION_ERROR": 422, "QUOTA_EXCEEDED": 429,
                  "AUTHORIZED_INPUT_UNAVAILABLE": 409}.get(error.code, 500)
        result = v1_err(status, error.code, error.message, stage="approval.decision")
        result.headers["Cache-Control"] = "no-store"
        return result

    @router.post("/runtime/approval-decisions")
    async def native_decision(body: NativeDecisionRequest, request: Request):
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        service = request.app.state.deps.native_decisions
        context = RuntimeRequestContext(agent.agent_id, "agent_key", credential_binding=agent.api_key_hash)
        try:
            view, replay = await anyio.to_thread.run_sync(lambda: service.confirm(
                context=context, request=body.model_dump()))
        except OktoNexusError as error:
            return native_error(error)
        return JSONResponse(view, status_code=200 if replay else 202, headers={"Cache-Control": "no-store"})

    @router.get("/runtime/approval-decisions/{decision_id}")
    async def native_decision_view(decision_id: str, request: Request):
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        service = request.app.state.deps.native_decisions
        context = RuntimeRequestContext(agent.agent_id, "agent_key", credential_binding=agent.api_key_hash)
        try:
            view = await anyio.to_thread.run_sync(lambda: service.read(context=context, decision_id=decision_id))
        except OktoNexusError as error:
            return native_error(error)
        return JSONResponse(view, headers={"Cache-Control": "no-store"})

    @router.get("/runtime/sessions/{session_id}/capability")
    async def capability_metadata(session_id: str, request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        query = request.query_params
        required = {"binding_id", "capability_id", "request_id"}
        if set(query) != required or len(query.multi_items()) != len(required):
            return v1_err(422, "VALIDATION_ERROR", "Invalid capability metadata query.")
        deps = request.app.state.deps
        service = ExecutionCapabilityService(factory=deps.connection_factory,
                                             access=build_execution_access(deps))
        try:
            metadata = await anyio.to_thread.run_sync(lambda: service.describe(
                context=RuntimeRequestContext(agent.agent_id, "agent_key",
                                              credential_binding=agent.api_key_hash),
                session_id=session_id, **dict(query),
                mcp_url=str(request.base_url).rstrip("/") + "/mcp"))
        except OktoNexusError as error:
            status = {"NOT_FOUND": 404, "PERMISSION_DENIED": 403, "CONFLICT": 409,
                      "VALIDATION_ERROR": 422}.get(error.code, 500)
            response = v1_err(status, error.code, error.message, stage="capability.metadata")
            response.headers['Cache-Control'] = 'no-store'
            return response
        return JSONResponse(metadata, headers={"Cache-Control": "no-store"})

    @router.post("/runtime/sessions/{session_id}/capability")
    async def session_capability(session_id: str, body: CapabilityRequest,
                                 request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        deps = request.app.state.deps
        service = ExecutionCapabilityService(factory=deps.connection_factory,
                                             access=build_execution_access(deps))
        try:
            issued = await anyio.to_thread.run_sync(lambda: service.issue(
                context=RuntimeRequestContext(agent.agent_id, "agent_key",
                                              credential_binding=agent.api_key_hash),
                session_id=session_id, request=body.model_dump(exclude_none=True),
                mcp_url=str(request.base_url).rstrip("/") + "/mcp"))
        except OktoNexusError as error:
            status = {"NOT_FOUND": 404, "PERMISSION_DENIED": 403, "CONFLICT": 409,
                      "CREDENTIAL_MATERIAL_UNAVAILABLE": 409, "VALIDATION_ERROR": 422}.get(error.code, 500)
            if error.code == 'CREDENTIAL_MATERIAL_UNAVAILABLE':
                return JSONResponse({'error': {
                    'code': error.code, 'stage': 'capability.issue', 'message': error.message,
                    'possible_effect': False, 'retry_safe': False, 'operation_id': None,
                    'capability_id': error.details['capability_id'],
                    'recovery_allowed': error.details['recovery_allowed'],
                    'action': 'Request a replacement with a new capability_request_id.'
                    if error.details['recovery_allowed'] else 'Recover the existing executor configuration.',
                }}, status_code=status, headers={'Cache-Control': 'no-store'})
            response = v1_err(status, error.code, error.message, stage="capability.issue")
            response.headers['Cache-Control'] = 'no-store'
            return response
        return JSONResponse(issued, headers={"Cache-Control": "no-store"})

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
                                  body: RealizationPublishRequest | LocalRealizationPrepareRequest,
                                  request: Request) -> JSONResponse:
        token = extract_bearer(request)
        if token is None:
            return v1_err(401, "AUTH_FAILED",
                          "Authentication is required to prepare a realization.")
        factory = request.app.state.deps.connection_factory

        agent = get_authenticated_agent()

        def _publish():
            if isinstance(body, LocalRealizationPrepareRequest):
                if agent is None:
                    raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                          "An authenticated local operator is required.", {})
                from ....application.execution_local_realizations import stage_embedded_realization
                return stage_embedded_realization(factory,
                    owner=getattr(request.app.state, "embedded_inventory_owner", None),
                    executor_id=executor_id, access=build_execution_access(request.app.state.deps),
                    context=RuntimeRequestContext(agent.agent_id, "agent_key",
                                                   credential_binding=agent.api_key_hash),
                    request=body.model_dump())
            installation = ensure_execution_installation(factory)
            principal = verify_execution_ticket(
                factory, ticket=token, server_id=installation.server_id,
                executor_id=executor_id, scope="realization:publish",
            )
            return publish_executor_realization(
                factory, principal=principal, request=body.model_dump())

        try:
            publication = await anyio.to_thread.run_sync(_publish)
        except OktoNexusError as error:
            status = {ErrorCode.CONFLICT: 409, ErrorCode.PERMISSION_DENIED: 403,
                      ErrorCode.NOT_FOUND: 404, ErrorCode.VALIDATION_ERROR: 422}.get(error.code, 500)
            return v1_err(status, error.code, error.message, stage="realization.publish")
        return JSONResponse(
            publication.public_dict(),
            status_code=200 if publication.reused else 201,
            headers={"Cache-Control": "no-store"},
        )

    def runtime_error(error, stage):
        status = {ErrorCode.NOT_FOUND: 404, ErrorCode.PERMISSION_DENIED: 403,
                  ErrorCode.CONFLICT: 409, ErrorCode.VALIDATION_ERROR: 422}.get(error.code, 500)
        response = v1_err(status, error.code, error.message, stage=stage)
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.post("/runtime/intents:resolve")
    async def resolve_intent(body: ResolveIntentRequest,
                             request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        factory = request.app.state.deps.connection_factory
        try:
            resolution = await anyio.to_thread.run_sync(
                lambda: resolve_execution_intent(
                    factory, actor_agent_id=agent.agent_id,
                    request=body.model_dump(exclude_none=True),
                    remote_ready=protocol_info()["remote_execution_ready"],
                    fresh_publications=request.app.state.inventory_fresh_publications,
                    access=build_execution_access(request.app.state.deps),
                    context=RuntimeRequestContext(agent.agent_id, "agent_key", credential_binding=agent.api_key_hash)))
        except OktoNexusError as error:
            return runtime_error(error, "intent.resolve")
        return JSONResponse(resolution, headers={"Cache-Control": "no-store"})

    @router.get("/runtime/intents/{client_intent_id}")
    async def intent_view(client_intent_id: str,
                          request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        factory = request.app.state.deps.connection_factory
        try:
            view = await anyio.to_thread.run_sync(
                lambda: read_execution_intent(
                    factory, actor_agent_id=agent.agent_id,
                    client_intent_id=client_intent_id))
        except OktoNexusError as error:
            return runtime_error(error, "intent.read")
        return JSONResponse(view, headers={"Cache-Control": "no-store"})

    @router.post("/runtime/operations")
    async def submit_operation(body: OperationSubmitRequest,
                               request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        factory = request.app.state.deps.connection_factory
        try:
            view, reused = await anyio.to_thread.run_sync(
                lambda: submit_execution_operation(
                    factory, actor_agent_id=agent.agent_id,
                    request=body.model_dump(),
                    fresh_publications=request.app.state.inventory_fresh_publications,
                    remote_ready=protocol_info()["remote_execution_ready"],
                    access=build_execution_access(request.app.state.deps),
                    context=RuntimeRequestContext(agent.agent_id, "agent_key", credential_binding=agent.api_key_hash),
                ))
        except OktoNexusError as error:
            return runtime_error(error, "operation.admit")
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

    @router.get("/runtime/sessions/{session_id}")
    async def session_view(session_id: str, request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        query = request.query_params
        if set(query) - {"executor_id"} or len(query.multi_items()) != len(query):
            return v1_err(422, "VALIDATION_ERROR", "Invalid session query.")
        from ....application.execution_session_views import read_execution_session
        factory = request.app.state.deps.connection_factory
        def read():
            server_id = ensure_execution_installation(factory).server_id
            return read_execution_session(factory, server_id=server_id, session_id=session_id,
                context=RuntimeRequestContext(agent.agent_id, "agent_key", credential_binding=agent.api_key_hash),
                access=build_execution_access(request.app.state.deps), executor_id=query.get("executor_id"))
        try:
            view = await anyio.to_thread.run_sync(read)
        except OktoNexusError as error:
            return runtime_error(error, "session.read")
        return JSONResponse(view, headers={"Cache-Control": "no-store"})

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
                actor_agent_id=None if history_ticket is not None else agent.agent_id,
            ).public_view()

        try:
            view = await anyio.to_thread.run_sync(_read)
        except OktoNexusError as error:
            return runtime_error(error, "operation.read")
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
