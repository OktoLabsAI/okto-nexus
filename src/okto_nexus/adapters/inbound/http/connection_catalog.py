"""Operator connection catalog; direct runtime-management JSON, never cached."""
from functools import partial

import anyio
from fastapi import APIRouter, Query, Request
from starlette.responses import JSONResponse

from ....errors import ErrorCode, OktoNexusError
from .identity_ctx import runtime_request_context, current_operator
from .routes import _map_error


def build_router():
    router = APIRouter()

    @router.get('/connections/catalog')
    async def catalog(request: Request, workspace_id: str | None = None, agent_id: str | None = None,
            executor_id: str | None = None, execution_location: str | None = None,
            cursor: str | None = Query(None, max_length=2048), limit: int = Query(25, ge=1, le=100)):
        try:
            allowed = {'workspace_id', 'agent_id', 'executor_id', 'execution_location', 'cursor', 'limit'}
            if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in request.query_params):
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Unknown or repeated connection catalog parameter.', {})
            from ....bootstrap.connection_catalog import build_connection_catalog
            service = getattr(request.app.state, 'connection_catalog', None) or build_connection_catalog(request.app.state.deps)
            value = await anyio.to_thread.run_sync(partial(service.read, context=runtime_request_context(),
                principal=current_operator.get(), filters=dict(workspace_id=workspace_id, agent_id=agent_id,
                    executor_id=executor_id, execution_location=execution_location), cursor=cursor, limit=limit))
            response = JSONResponse(value)
        except OktoNexusError as error:
            response = _map_error(error)
        response.headers['Cache-Control'] = 'no-store'
        return response

    return router
