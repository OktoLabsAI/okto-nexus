"""Optional entries router. Root application integration is a separate step."""
from functools import partial

import anyio.to_thread
from fastapi import APIRouter, Request

from ....errors import ErrorCode, OktoNexusError
from .identity_ctx import runtime_request_context, current_operator
from .routes import _map_error, _ok


FILTERS = frozenset({'workspace_id', 'agent_id', 'state', 'quick', 'harness', 'host'})


async def call(request, *, partition, group_id=None, entry_id=None):
    try:
        allowed = FILTERS | {'cursor', 'limit', 'preview', 'api_key'}
        if partition == 'board' or partition.startswith('harness_'):
            allowed = allowed - {'quick'}
        if partition != 'board':
            allowed = allowed | {'presentation_version'}
        if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Unknown or repeated Home entries parameter.', {})
        try:
            limit = int(request.query_params.get('limit', '10'))
            preview = int(request.query_params.get('preview', '3'))
        except ValueError:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid Home entries page size.', {}) from None
        version = request.query_params.get('presentation_version', '1')
        if version not in ('1', '2'):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Unsupported Home presentation version.', {})
        extra = {'presentation_version': int(version)} if partition != 'board' else {}
        value = await anyio.to_thread.run_sync(partial(request.app.state.home_entries.read,
            context=runtime_request_context(), principal=current_operator.get(),
            filters={k: request.query_params[k] for k in FILTERS if k in request.query_params},
            partition=partition, group_id=group_id, entry_id=entry_id,
            cursor=request.query_params.get('cursor'), limit=limit, preview=preview, **extra))
        response = _ok(value)
    except OktoNexusError as exc:
        response = _map_error(exc)
    response.headers['Cache-Control'] = 'no-store'
    return response


def build_router():
    router = APIRouter()

    @router.get('/home/harness-board')
    async def harness_board(request: Request):
        return await call(request, partition='harness_board')

    @router.get('/home/harness-board/unlinked')
    async def harness_unlinked(request: Request):
        return await call(request, partition='harness_unlinked')

    @router.get('/home/harness-board/cards/{card_id}/children')
    async def harness_children(request: Request, card_id: str):
        return await call(request, partition='harness_children', group_id=card_id)

    @router.get('/home/harness-board/cards/{card_id}/requests')
    async def harness_requests(request: Request, card_id: str):
        return await call(request, partition='harness_requests', group_id=card_id)

    @router.get('/home/harness-board/cards/{card_id}/sessions')
    async def harness_sessions(request: Request, card_id: str):
        return await call(request, partition='harness_sessions', group_id=card_id)

    @router.get('/home/harness-board/{column}')
    async def harness_column(request: Request, column: str):
        return await call(request, partition='harness_board', group_id=column)

    @router.get('/home/board')
    async def board(request: Request):
        return await call(request, partition='board')

    @router.get('/home/board/{column}')
    async def board_column(request: Request, column: str):
        return await call(request, partition='board', group_id=column)

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
