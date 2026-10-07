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
from ....application.execution_inventory_refresh import request_inventory_refresh, claim_remote_inventory_refresh
from ....application.execution_realizations import publish_executor_realization
from ....application.execution_intents import (
    read_execution_intent, resolve_execution_intent,
)
from ....application.execution_admission import submit_execution_operation
from ....application.execution_capabilities import ExecutionCapabilityService
from ....bootstrap.execution_authority import build_execution_access
from ....application.executor_inventory_views import (
    read_executor_inventory,
)
from ....application.execution_runtime_options import read_runtime_options
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
from .identity_ctx import get_authenticated_agent, runtime_request_context, trusted_local_operator


MAX_INVENTORY_BODY_BYTES = 1024 * 1024
MAX_RECEIPT_BODY_BYTES = 64 * 1024

_Id = Annotated[str, Field(min_length=1, max_length=160, strict=True)]
_Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$", strict=True)]
_CandidateRef = Annotated[str, Field(
    pattern=r"^nexus-install-v1:[0-9a-f]{64}$", strict=True)]


class InventoryRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_intent_id: _Id


class ConnectionSetupRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    client_intent_id: Annotated[str, Field(min_length=1, max_length=100)]
    agent_id: _Id
    executor_id: str = ''
    candidate_ref: str = ''
    inventory_revision: str = ''
    workspace_id: str | None = None
    binding_id: str | None = None
    baseline: dict[str, int | None]
    configuration: dict


class LocalInstallationCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    agent_id: _Id
    adapter_id: _Id
    candidate_ref: _CandidateRef
    inventory_revision: _Digest
    approved: bool


class InventoryRefreshClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    producer_instance_id: _Id


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
    agent_id: _Id | None = None
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


class ShutdownRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    timeout_seconds: Annotated[float, Field(ge=0, le=300, allow_inf_nan=False)] = 50.0


class CapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_request_id: _Id
    binding_id: _Id
    audience: _Id
    actions: Annotated[list[_Id], Field(max_length=128)]
    replaces_capability_id: _Id | None = None


class RecoveryConfirmation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    plan: dict
    confirmation: Literal['PREVIOUS_RUNTIME_PROCESSES_STOPPED']


def build_router() -> APIRouter:
    router = APIRouter()

    async def shutdown_authority(request, *, mutate):
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        access = build_execution_access(request.app.state.deps)
        context = runtime_request_context()
        def authorize():
            if mutate:
                access.authorize_maintenance(context)
            else:
                with access.cf.unit_of_work(write=False) as uow:
                    if not access.authenticate(context, uow=uow, require_feature=False):
                        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                            "Operator authority is required for shutdown recovery.", {})
        try:
            await anyio.to_thread.run_sync(authorize)
        except OktoNexusError as error:
            return v1_err(403, error.code, error.message)
        return None

    @router.get("/runtime/recovery/plan")
    async def runtime_recovery_plan(request: Request, agent_id: str | None = None):
        denied = await shutdown_authority(request, mutate=True)
        if denied is not None:
            return denied
        owner = getattr(request.app.state, 'embedded_dispatch_owner', None)
        if owner is None:
            return v1_err(503, 'RECONCILIATION_REQUIRED', 'The local runtime owner is unavailable.')
        try:
            return JSONResponse(await owner.recovery_plan(agent_id), headers={'Cache-Control': 'no-store'})
        except Exception as error:
            return v1_err(409, getattr(error, 'code', 'RECONCILIATION_REQUIRED'),
                'A safe recovery plan could not be prepared. Retained history was preserved.')

    @router.post("/runtime/recovery/confirm-stopped")
    async def confirm_runtime_stopped(body: RecoveryConfirmation, request: Request):
        denied = await shutdown_authority(request, mutate=True)
        if denied is not None:
            return denied
        owner = getattr(request.app.state, 'embedded_dispatch_owner', None)
        if owner is None:
            return v1_err(503, 'RECONCILIATION_REQUIRED', 'The local runtime owner is unavailable.')
        try:
            view = await owner.confirm_recovery(body.plan, get_authenticated_agent().agent_id)
        except Exception as error:
            return v1_err(409, getattr(error, 'code', 'RECONCILIATION_REQUIRED'),
                'Recovery state changed or remains unresolved. Review a new plan before continuing.')
        return JSONResponse(view, headers={'Cache-Control': 'no-store'})

    @router.post("/runtime/recovery/retry")
    async def retry_runtime_recovery(request: Request, agent_id: str | None = None):
        denied = await shutdown_authority(request, mutate=True)
        if denied is not None:
            return denied
        owner = getattr(request.app.state, 'embedded_dispatch_owner', None)
        if owner is None:
            return v1_err(503, 'RECONCILIATION_REQUIRED', 'The local runtime owner is unavailable.')
        try:
            view = await owner.retry_recovery(agent_id)
        except OktoNexusError as error:
            return v1_err(409, error.code, error.message)
        return JSONResponse(view, headers={'Cache-Control': 'no-store'})

    @router.post("/runtime/shutdown")
    async def request_shutdown(body: ShutdownRequest, request: Request):
        denied = await shutdown_authority(request, mutate=True)
        if denied is not None:
            return denied
        owner = getattr(request.app.state, "runtime_shutdown", None)
        if owner is None:
            return v1_err(503, "RECONCILIATION_REQUIRED", "The shutdown owner is unavailable.")
        view = await owner.request(timeout_seconds=body.timeout_seconds)
        return JSONResponse(view, status_code=200 if view["state"] == "DRAINED" else 202,
                            headers={"Cache-Control": "no-store"})

    @router.get("/runtime/shutdown")
    async def shutdown_status(request: Request):
        denied = await shutdown_authority(request, mutate=False)
        if denied is not None:
            return denied
        owner = getattr(request.app.state, "runtime_shutdown", None)
        if owner is None:
            return v1_err(503, "RECONCILIATION_REQUIRED", "The shutdown owner is unavailable.")
        return JSONResponse(owner.status(), headers={"Cache-Control": "no-store"})

    def native_error(error):
        status = {"NOT_FOUND": 404, "PERMISSION_DENIED": 403, "APPROVAL_AUTHORITY_REQUIRED": 403,
                  "CONFLICT": 409, "VALIDATION_ERROR": 422, "QUOTA_EXCEEDED": 429,
                  "AUTHORIZED_INPUT_UNAVAILABLE": 409}.get(error.code, 500)
        result = v1_err(status, error.code, error.message, stage="approval.decision")
        result.headers["Cache-Control"] = "no-store"
        if error.code == ErrorCode.QUOTA_EXCEEDED:
            result.headers["Retry-After"] = "1"
        return result

    @router.get("/runtime/input-requests")
    async def native_input_requests(request: Request, workspace_id: str | None = None):
        if get_authenticated_agent() is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        service = request.app.state.deps.native_decisions
        context = runtime_request_context()
        try:
            items = await anyio.to_thread.run_sync(lambda: service.pending_inputs(
                context=context, workspace_id=workspace_id))
        except OktoNexusError as error:
            return native_error(error)
        return JSONResponse({"items": items}, headers={"Cache-Control": "no-store"})

    @router.post("/runtime/approval-decisions")
    async def native_decision(body: NativeDecisionRequest, request: Request):
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        service = request.app.state.deps.native_decisions
        context = runtime_request_context()
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
        context = runtime_request_context()
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
                context=runtime_request_context(),
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
                context=runtime_request_context(),
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

    @router.post("/runtime/executors/{executor_id}/inventory:refresh")
    async def refresh_inventory(executor_id: str, body: InventoryRefreshRequest,
                                request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        if request.query_params:
            return v1_err(422, "VALIDATION_ERROR", "Query parameters are not supported.")
        deps = request.app.state.deps
        def _request():
            return request_inventory_refresh(deps.connection_factory,
                context=runtime_request_context(),
                access=build_execution_access(deps),
                server_id=ensure_execution_installation(deps.connection_factory).server_id,
                executor_id=executor_id, client_intent_id=body.client_intent_id)
        try:
            view = await anyio.to_thread.run_sync(_request)
        except OktoNexusError as error:
            return runtime_error(error, 'inventory.refresh')
        return JSONResponse(view, status_code=202, headers={"Cache-Control": "no-store"})

    @router.post("/runtime/executors/{executor_id}/inventory:claim-refresh")
    async def claim_refresh(executor_id: str, body: InventoryRefreshClaim,
                            request: Request) -> JSONResponse:
        token = extract_bearer(request)
        if token is None:
            return v1_err(401, "AUTH_FAILED", "An execution ticket is required.")
        if request.query_params or request.headers.get('x-api-key'):
            return v1_err(422, "VALIDATION_ERROR", "Use only the execution bearer ticket.")
        factory = request.app.state.deps.connection_factory
        def _claim():
            installation = ensure_execution_installation(factory)
            verified = verify_execution_ticket(factory, ticket=token, server_id=installation.server_id,
                executor_id=executor_id, scope='inventory:publish')
            delivery = claim_remote_inventory_refresh(factory,
                principal=ExecutorKey(installation.server_id, executor_id),
                publication_ticket_id=verified.ticket_id, producer_instance_id=body.producer_instance_id)
            return dict(server_id=installation.server_id, executor_id=executor_id,
                        producer_instance_id=body.producer_instance_id, delivery_id=delivery)
        try:
            view = await anyio.to_thread.run_sync(_claim)
        except OktoNexusError as error:
            return runtime_error(error, 'inventory.refresh.claim')
        return JSONResponse(view, headers={"Cache-Control": "no-store"})

    @router.put("/runtime/executors/{executor_id}/inventory")
    async def publish_inventory(executor_id: str,
                                request: Request) -> JSONResponse:
        token = extract_bearer(request)
        if token is None:
            return v1_err(401, "AUTH_FAILED",
                          "An execution ticket is required.")
        refresh_delivery_id = request.headers.get('X-Nexus-Inventory-Refresh')
        if refresh_delivery_id is not None and not 1 <= len(refresh_delivery_id) <= 160:
            return v1_err(422, "VALIDATION_ERROR", "Invalid inventory refresh delivery ID.")
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
                refresh_delivery_id=refresh_delivery_id,
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
                context=runtime_request_context(),
                access=build_execution_access(request.app.state.deps),
            )

        try:
            view = await anyio.to_thread.run_sync(_read)
        except OktoNexusError as error:
            return runtime_error(error, 'inventory.read')
        return JSONResponse(view, headers={"Cache-Control": "no-store"})

    @router.post("/runtime/executors/{executor_id}/realizations")
    async def publish_realization(executor_id: str,
                                  body: RealizationPublishRequest | LocalRealizationPrepareRequest,
                                  request: Request) -> JSONResponse:
        token = extract_bearer(request)
        if token is None and not (trusted_local_operator.get() and isinstance(body, LocalRealizationPrepareRequest)):
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
                    context=runtime_request_context(),
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
                  'SCOPE_MISMATCH': 403,
                  ErrorCode.CONFLICT: 409, ErrorCode.VALIDATION_ERROR: 422,
                    ErrorCode.QUOTA_EXCEEDED: 429, 'CAPACITY_EXCEEDED': 429}.get(error.code, 500)
        response = v1_err(status, error.code, error.message, stage=stage)
        response.headers["Cache-Control"] = "no-store"
        if error.code == ErrorCode.QUOTA_EXCEEDED:
            response.headers["Retry-After"] = "1"
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
                    context=runtime_request_context()))
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
                    client_intent_id=client_intent_id,
                    access=build_execution_access(request.app.state.deps),
                    context=runtime_request_context()))
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
                    context=runtime_request_context(),
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

    @router.get("/runtime/sessions")
    async def session_list(request: Request, executor_id: str, binding_id: str,
                           agent_id: str, after_session_id: str = "", limit: int = 25) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        query = request.query_params
        if (set(query) - {"executor_id", "binding_id", "agent_id", "after_session_id", "limit"}
                or len(query.multi_items()) != len(query)):
            return v1_err(422, "VALIDATION_ERROR", "Invalid session list query.")
        from ....application.execution_session_views import list_execution_sessions
        deps = request.app.state.deps
        def read():
            return list_execution_sessions(deps.connection_factory,
                server_id=ensure_execution_installation(deps.connection_factory).server_id,
                context=runtime_request_context(),
                access=build_execution_access(deps), executor_id=executor_id,
                binding_id=binding_id, agent_id=agent_id, after_session_id=after_session_id, limit=limit)
        try:
            result = await anyio.to_thread.run_sync(read)
        except OktoNexusError as error:
            return runtime_error(error, "session.list")
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

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
                context=runtime_request_context(),
                access=build_execution_access(request.app.state.deps), executor_id=query.get("executor_id"))
        try:
            view = await anyio.to_thread.run_sync(read)
        except OktoNexusError as error:
            return runtime_error(error, "session.read")
        return JSONResponse(view, headers={"Cache-Control": "no-store"})

    @router.get("/runtime/sessions/{session_id}/events")
    async def session_events(session_id: str, request: Request, after_sequence: int = 0,
                             limit: int = 200, executor_id: str | None = None,
                             stream_epoch: str | None = None) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        query = request.query_params
        if (set(query) - {"after_sequence", "limit", "executor_id", "stream_epoch"}
                or len(query.multi_items()) != len(query)):
            return v1_err(422, "VALIDATION_ERROR", "Invalid event query.")
        from ....bootstrap.execution_compat import events_view
        context = runtime_request_context()
        try:
            result = await anyio.to_thread.run_sync(lambda: events_view(request.app.state.deps,
                context, session_id, after_sequence=after_sequence, limit=limit,
                executor_id=executor_id, stream_epoch=stream_epoch))
        except OktoNexusError as error:
            return runtime_error(error, "session.events")
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

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

    @router.get("/agents/{agent_id}/executors")
    async def agent_executors(agent_id: str, request: Request,
                              after_executor_id: str | None = None, limit: int = 50) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, 'AUTH_FAILED', 'Authentication is required.')
        query = request.query_params
        if set(query) - {'after_executor_id', 'limit'} or len(query.multi_items()) != len(query):
            return v1_err(422, 'VALIDATION_ERROR', 'Invalid executor directory query.')
        factory = request.app.state.deps.connection_factory

        def _read():
            from ....application.executor_directory import list_agent_executors
            return list_agent_executors(factory,
                server_id=ensure_execution_installation(factory).server_id,
                agent_id=agent_id, after_executor_id=after_executor_id, limit=limit,
                context=runtime_request_context(),
                access=build_execution_access(request.app.state.deps))

        try:
            view = await anyio.to_thread.run_sync(_read)
        except OktoNexusError as error:
            return runtime_error(error, 'executors.read')
        return JSONResponse(view, headers={'Cache-Control': 'no-store'})

    @router.post("/runtime/executors/{executor_id}/installations:check")
    async def check_local_installation(executor_id: str, body: LocalInstallationCheckRequest,
                                       request: Request) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        owner = getattr(request.app.state, "embedded_inventory_owner", None)
        if owner is None or owner.key.executor_id != executor_id:
            return v1_err(403, "PERMISSION_DENIED", "Version checks require this Server's local executor.")
        try:
            view = await owner.check_installation(access=build_execution_access(request.app.state.deps),
                context=runtime_request_context(),
                request=body.model_dump())
        except OktoNexusError as error:
            return runtime_error(error, 'installation.check')
        return JSONResponse(view, headers={"Cache-Control": "no-store"})

    @router.get("/agents/{agent_id}/runtime-options")
    async def runtime_options(agent_id: str, executor_id: str,
                              request: Request, workspace_id: str | None = None) -> JSONResponse:
        agent = get_authenticated_agent()
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        query = request.query_params
        if set(query) - {'executor_id', 'workspace_id'} or len(query.multi_items()) != len(query):
            return v1_err(422, 'VALIDATION_ERROR', 'Invalid runtime-options query.')
        factory = request.app.state.deps.connection_factory

        def _read():
            server_id = ensure_execution_installation(factory).server_id
            return read_runtime_options(
                factory, server_id=server_id, executor_id=executor_id,
                agent_id=agent_id, workspace_id=workspace_id,
                fresh_publications=request.app.state.inventory_fresh_publications,
                context=runtime_request_context(),
                access=build_execution_access(request.app.state.deps),
                remote_ready=protocol_info()['remote_execution_ready'],
            )

        try:
            view = await anyio.to_thread.run_sync(_read)
        except OktoNexusError as error:
            return runtime_error(error, 'runtime-options.read')
        return JSONResponse(view, headers={"Cache-Control": "no-store"})

    @router.get('/connections/setup/{agent_id}')
    async def connection_setup_read(agent_id: str, request: Request, binding_id: str | None = None):
        from ....application.connection_setup import load_setup
        try:
            result = await anyio.to_thread.run_sync(lambda: load_setup(request.app.state.deps,
                runtime_request_context(), agent_id, binding_id))
            return JSONResponse(result, headers={'Cache-Control':'no-store'})
        except OktoNexusError as error:
            return runtime_error(error, 'connection.setup')

    @router.get('/workspaces/{workspace_id}/paths')
    async def workspace_paths_read(workspace_id: str, executor_id: str, request: Request):
        from ....application.workspace_paths import list_workspace_paths
        try:
            result = await anyio.to_thread.run_sync(lambda: list_workspace_paths(
                request.app.state.deps, runtime_request_context(),
                workspace_id=workspace_id, executor_id=executor_id))
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except OktoNexusError as error:
            return runtime_error(error, 'workspace.paths')

    def setup_request(body):
        from nexus_connector_core.connection_configuration import parse_connection_configuration
        from nexus_connector_core import CoreError
        result = body.model_dump()
        try:
            from ....application.connection_authorization import normalize_authorization
            result['configuration'] = normalize_authorization(parse_connection_configuration(normalize_authorization(result['configuration'])))
        except (CoreError, ValueError, TypeError):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid connection configuration file.', {}) from None
        return result

    @router.post('/connections/setup:test')
    async def connection_setup_test(body: ConnectionSetupRequest, request: Request):
        from nexus_connector_core import CoreError
        try:
            result = request.app.state.connection_tests.start(runtime_request_context(),
                getattr(request.app.state,'embedded_inventory_owner',None), setup_request(body))
            return JSONResponse(result, headers={'Cache-Control':'no-store'})
        except CoreError as error:
            return v1_err(409, error.code, 'Refresh installations and review the selected runtime.')
        except OktoNexusError as error:
            return runtime_error(error, 'connection.test')

    @router.get('/connections/setup-tests/{test_id}')
    async def connection_setup_test_read(test_id: str, request: Request):
        manager = request.app.state.connection_tests
        try:
            return JSONResponse(manager.public(manager.get(runtime_request_context(), test_id)),
                headers={'Cache-Control':'no-store'})
        except OktoNexusError as error:
            return runtime_error(error, 'connection.test')

    @router.post('/connections/setup:finish')
    async def connection_setup_finish(body: ConnectionSetupRequest, request: Request):
        from ....application.connection_setup import finish_setup, require_operator, runtime_enabled
        from nexus_connector_core import CoreError
        try:
            value = setup_request(body)
            context = runtime_request_context()
            owner = getattr(request.app.state,'embedded_inventory_owner',None)
            # The application receipt handles successful retries after a restart.
            with request.app.state.deps.connection_factory.unit_of_work(write=False) as uow:
                require_operator(build_execution_access(request.app.state.deps), context, uow)
                prior = uow.connection.execute('SELECT 1 FROM connection_setup_commits WHERE actor_agent_id=? AND client_intent_id=?',
                    (context.actor_agent_id,value['client_intent_id'])).fetchone()
                active = runtime_enabled(uow.connection, value['configuration'])
            verified = None
            if not prior and active and value['configuration']['execution_location'] != 'remote':
                verified = request.app.state.connection_tests.verified(context, value, owner)
            result = await anyio.to_thread.run_sync(lambda: finish_setup(request.app.state.deps, context,
                owner, request.app.state.inventory_fresh_publications, value, verified=verified))
            return JSONResponse(result, headers={'Cache-Control':'no-store'})
        except CoreError as error:
            return v1_err(409, error.code, 'Refresh installations and test the selected runtime again.')
        except OktoNexusError as error:
            return runtime_error(error, 'connection.finish')

    return router
