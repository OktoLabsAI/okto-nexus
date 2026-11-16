"""Operator-only, read-only Home projection and exact-reference resolution."""
from functools import partial
import json

import anyio.to_thread
from fastapi import APIRouter, Depends, Query, Request

from ....errors import ErrorCode, OktoNexusError
from .identity_ctx import runtime_request_context
from .routes import _map_error, _ok


def filters(workspace_id: str | None = None, agent_id: str | None = None, state: str | None = None):
    return {k: v for k, v in dict(workspace_id=workspace_id, agent_id=agent_id, state=state).items() if v is not None}


async def call(request, method, allowed, **kwargs):
    try:
        if any(key not in allowed | {'api_key'} or len(request.query_params.getlist(key)) != 1
               for key in request.query_params):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Unknown or repeated Home parameter.', {})
        value = await anyio.to_thread.run_sync(partial(getattr(request.app.state.home, method),
            context=runtime_request_context(), **kwargs))
        response = _ok(value)
    except OktoNexusError as exc:
        response = _map_error(exc)
    response.headers['Cache-Control'] = 'no-store'
    return response


def build_router():
    router = APIRouter()
    keys = {'workspace_id', 'agent_id', 'state'}

    @router.get('/home/overview')
    async def overview(request: Request, scope: dict = Depends(filters),
            limit_work: int = Query(10, ge=1, le=100), limit_attention: int = Query(3, ge=1, le=100),
            limit_results: int = Query(6, ge=1, le=100), limit_agents: int = Query(6, ge=1, le=100)):
        return await call(request, 'read', keys | {'limit_work', 'limit_attention', 'limit_results', 'limit_agents'},
            filters=scope, limit_work=limit_work, limit_attention=limit_attention,
            limit_results=limit_results, limit_agents=limit_agents)

    def page_endpoint(section):
        async def page(request: Request, scope: dict = Depends(filters), cursor: str | None = None,
                       limit: int = Query(20, ge=1, le=100)):
            return await call(request, 'read', keys | {'cursor', 'limit'},
                section=section, filters=scope, cursor=cursor, limit=limit)
        return page

    for section in ('work', 'results', 'activity', 'agents', 'external', 'attention', 'server_attention'):
        router.add_api_route('/home/' + section.replace('_', '-'), page_endpoint(section), methods=['GET'], name='home_' + section)

    @router.get('/home/target')
    async def target(request: Request, target: str = Query(max_length=4096), workspace_id: str | None = None):
        try:
            value = json.loads(target)
        except ValueError:
            response = _map_error(OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid Home target JSON.', {}))
            response.headers['Cache-Control'] = 'no-store'
            return response
        return await call(request, 'resolve', {'target', 'workspace_id'}, target=value, workspace_id=workspace_id)

    return router
