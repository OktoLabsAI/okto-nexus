"""Ticket-authenticated R4 technical inventory transport."""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from nexus_connector_core.protocol import strict_json

from ....application.executor_inventory import publish_executor_inventory
from ....domain.execution.keys import ExecutorKey
from ...outbound.sqlite.execution_identity import ensure_execution_installation
from ...outbound.sqlite.execution_tickets import verify_execution_ticket
from .app import extract_bearer, v1_err


MAX_INVENTORY_BODY_BYTES = 1024 * 1024


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
        return JSONResponse({
            "server_id": publication.server_id,
            "executor_id": publication.executor_id,
            "publication_sequence": publication.publication_sequence,
            "inventory_revision": publication.inventory_revision,
            "fresh_for_ms": max(0, 120_000 - snapshot["observation_age_ms"]),
            "accepted": True,
        }, headers={"Cache-Control": "no-store"})

    return router
