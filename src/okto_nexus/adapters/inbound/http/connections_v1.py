"""Direct-object R4 connection protocol endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ...outbound.execution.core_inventory import (
    MANAGEMENT_REVISION, protocol_info,
)


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/connections/protocol")
    async def protocol() -> JSONResponse:
        response = JSONResponse(protocol_info())
        response.headers["X-Nexus-Connections-Revision"] = MANAGEMENT_REVISION
        return response

    return router
