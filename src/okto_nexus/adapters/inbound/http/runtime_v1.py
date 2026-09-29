"""Ticket-authenticated R4 technical inventory transport."""

from __future__ import annotations

import anyio
import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from nexus_connector_core.protocol import strict_json

from ....application.executor_inventory import publish_executor_inventory
from ....application.executor_inventory_views import (
    read_executor_inventory, runtime_options_from_inventory,
)
from ....domain.execution.keys import ExecutorKey
from ...outbound.sqlite.execution_receipts import (
    append_execution_receipt, read_execution_operation_history,
)
from ...outbound.sqlite.execution_identity import ensure_execution_installation
from ...outbound.sqlite.execution_tickets import verify_execution_ticket
from .app import extract_bearer, v1_err
from .identity_ctx import get_authenticated_agent


MAX_INVENTORY_BODY_BYTES = 1024 * 1024
MAX_RECEIPT_BODY_BYTES = 64 * 1024


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
            verify_execution_ticket(
                factory, ticket=token, server_id=installation.server_id,
                executor_id=executor_id, scope="inventory:publish",
            )
            return publish_executor_inventory(
                factory, principal=ExecutorKey(installation.server_id,
                                               executor_id),
                producer_instance_id=snapshot.get("producer_instance_id"),
                snapshot=snapshot,
            )

        publication = await anyio.to_thread.run_sync(_publish)
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
        if agent is None:
            return v1_err(401, "AUTH_FAILED", "Authentication is required.")
        factory = request.app.state.deps.connection_factory

        def _read():
            server_id = ensure_execution_installation(factory).server_id
            return read_execution_operation_history(
                factory, server_id=server_id, executor_id=None,
                operation_id=operation_id, subject_agent_id=agent.agent_id,
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
