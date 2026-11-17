"""Operator-only public connection namespace and project proof transport."""
import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ....errors import ErrorCode, OktoNexusError
from .identity_ctx import current_operator, runtime_request_context


class ReserveRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    approved: bool
    request: dict


class AssociateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    approved: bool
    client_intent_id: str = Field(min_length=1, max_length=100)
    connect_id: str = Field(min_length=1, max_length=64)
    expected_binding_ref: dict
    expected_binding_revision: int = Field(ge=1)


def build_router(runtime_error, normalize_request, request_model):
    router = APIRouter()

    def query_keys(request, allowed):
        if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Unknown or repeated connection parameter.', {})

    @router.get('/connections/public-ids')
    async def public_ids(request: Request, workspace_id: str | None = None, connect_id: str | None = None,
                         limit: int = 100, cursor: str | None = None):
        from ....application.connection_public_ids import list_public_ids
        try:
            query_keys(request, {'workspace_id', 'connect_id', 'limit', 'cursor'})
            value = await anyio.to_thread.run_sync(lambda: list_public_ids(request.app.state.deps,
                runtime_request_context(), workspace_id=workspace_id, requested_id=connect_id,
                limit=limit, cursor=cursor, principal=current_operator.get()))
            return JSONResponse(value, headers={'Cache-Control': 'no-store'})
        except OktoNexusError as error:
            return runtime_error(error, 'connection.public_ids')

    @router.get('/connections/project-context')
    @router.get('/connections/public-ids/project-revision')
    async def project_context(request: Request, executor_id: str, workspace_id: str | None = None,
                              project_root: str | None = None, root: str | None = None):
        from ....application.connection_project_context import read_project_context
        try:
            query_keys(request, {'executor_id', 'workspace_id', 'project_root', 'root'})
            if project_root is not None and root is not None:
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Use one project root parameter.', {})
            value = await anyio.to_thread.run_sync(lambda: read_project_context(request.app.state.deps,
                runtime_request_context(), executor_id=executor_id, workspace_id=workspace_id,
                project_root=project_root if project_root is not None else root))
            return JSONResponse(value, headers={'Cache-Control': 'no-store'})
        except OktoNexusError as error:
            return runtime_error(error, 'connection.project_context')

    @router.post('/connections/public-ids/reserve')
    async def reserve(request: Request, body: ReserveRequest):
        from ....application.connection_public_ids import reserve_public_id
        try:
            value = normalize_request(request_model.model_validate(body.request))
            result = await anyio.to_thread.run_sync(lambda: reserve_public_id(request.app.state.deps,
                runtime_request_context(), value, approved=body.approved))
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except ValidationError:
            return runtime_error(OktoNexusError(ErrorCode.VALIDATION_ERROR,
                'Invalid approved connection setup request.', {}), 'connection.public_ids.reserve')
        except OktoNexusError as error:
            return runtime_error(error, 'connection.public_ids.reserve')

    @router.post('/connections/public-ids/associate-existing')
    async def associate(request: Request, body: AssociateRequest):
        from ....application.connection_public_ids import associate_existing
        try:
            result = await anyio.to_thread.run_sync(lambda: associate_existing(request.app.state.deps,
                runtime_request_context(), body.model_dump()))
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except OktoNexusError as error:
            return runtime_error(error, 'connection.public_ids.associate')

    return router
