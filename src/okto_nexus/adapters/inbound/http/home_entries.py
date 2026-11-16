"""Optional entries router. Root application integration is a separate step."""
from functools import partial

import anyio.to_thread
from fastapi import APIRouter, Request

from ....errors import ErrorCode, OktoNexusError
from .identity_ctx import runtime_request_context
from .routes import _map_error, _ok


FILTERS = frozenset({'workspace_id', 'agent_id', 'state', 'quick', 'harness', 'host'})


async def call(request, *, partition, group_id=None, entry_id=None):
    try:
        allowed = FILTERS | {'cursor', 'limit', 'preview', 'api_key'}
        if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Unknown or repeated Home entries parameter.', {})
        try:
            limit = int(request.query_params.get('limit', '10'))
            preview = int(request.query_params.get('preview', '3'))
        except ValueError:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid Home entries page size.', {}) from None
        value = await anyio.to_thread.run_sync(partial(request.app.state.home_entries.read,
            context=runtime_request_context(), filters={k: request.query_params[k] for k in FILTERS if k in request.query_params},
            partition=partition, group_id=group_id, entry_id=entry_id,
            cursor=request.query_params.get('cursor'), limit=limit, preview=preview))
        response = _ok(value)
    except OktoNexusError as exc:
        response = _map_error(exc)
    response.headers['Cache-Control'] = 'no-store'
    return response


def build_router():
    router = APIRouter()

    @router.get('/home/entries')
    async def groups(request: Request):
        return await call(request, partition='groups')

    @router.get('/home/entries/{group_id}/children')
    async def children(request: Request, group_id: str):
        return await call(request, partition='children', group_id=group_id)

    @router.get('/home/entries/{group_id}/children/{entry_id}/sessions')
    async def sessions(request: Request, group_id: str, entry_id: str):
        return await call(request, partition='sessions', group_id=group_id, entry_id=entry_id)

    @router.get('/home/entries/{group_id}/children/{entry_id}/attention')
    async def attention(request: Request, group_id: str, entry_id: str):
        return await call(request, partition='attention', group_id=group_id, entry_id=entry_id)

    @router.get('/home/entries/{group_id}/children/{entry_id}/results')
    async def results(request: Request, group_id: str, entry_id: str):
        return await call(request, partition='results', group_id=group_id, entry_id=entry_id)

    return router
