"""Connection settings and the deliberately narrow bearer bootstrap route."""
import anyio
from fastapi import APIRouter, Request

from ....application.agent_connections import AgentConnectionService
from ....errors import ErrorCode, OktoNexusError
from ..runtime_admin import RuntimeAdminBody


class PolicyBody(RuntimeAdminBody):
    expected_revision: int
    methods: dict[str, bool]
    key_ttl_seconds: int | None = None


class KeyBody(RuntimeAdminBody):
    endpoint_id: str


class ConnectBody(RuntimeAdminBody):
    endpoint_id: str
    idempotency_key: str


class OpenBody(RuntimeAdminBody):
    pass


def service(deps):
    from ..mcp.tools.harness import build_access_service
    return AgentConnectionService(build_access_service(deps))


def build_router():
    from ..mcp.tools.harness import (
        build_open_service,
        is_local_runtime_owner,
        request_context,
    )
    from .app import extract_bearer
    from .routes import _map_error, _ok
    router = APIRouter()

    async def execute(fn):
        try:
            return _ok(await anyio.to_thread.run_sync(fn))
        except OktoNexusError as exc:
            return _map_error(exc)

    @router.get('/connections/available')
    async def available(request: Request):
        return await execute(lambda: service(request.app.state.deps).available(request_context()))

    @router.post('/connections/connect')
    async def connect(request: Request, body: ConnectBody):
        from ..mcp.tools.harness import connect_own_endpoint
        return await execute(lambda: connect_own_endpoint(request.app.state.deps, **body.model_dump()))

    @router.get('/agents/{agent_id}/connections')
    async def view(request: Request, agent_id: str):
        return await execute(lambda: service(request.app.state.deps).view(request_context(), agent_id=agent_id))

    @router.put('/agents/{agent_id}/connections')
    async def configure(request: Request, agent_id: str, body: PolicyBody):
        return await execute(lambda: service(request.app.state.deps).configure(request_context(), agent_id=agent_id, **body.model_dump()))

    @router.post('/agents/{agent_id}/connection-keys')
    async def issue(request: Request, agent_id: str, body: KeyBody):
        result = await execute(lambda: service(request.app.state.deps).issue(request_context(), agent_id=agent_id, **body.model_dump()))
        result.headers['Cache-Control'] = 'no-store'
        return result

    @router.delete('/agents/{agent_id}/connection-keys/{key_id}')
    async def revoke(request: Request, agent_id: str, key_id: str):
        return await execute(lambda: service(request.app.state.deps).revoke(request_context(), agent_id=agent_id, key_id=key_id))

    @router.post('/connections/open')
    async def opening(request: Request, body: OpenBody):
        def run():
            deps = request.app.state.deps
            connections = service(deps)
            context, arguments = connections.resolve(extract_bearer(request))
            connections.access.authorize(context, action="open", endpoint_id=arguments["endpoint_id"])
            if not is_local_runtime_owner(deps):
                raise OktoNexusError(ErrorCode.CONFLICT,
                    "Restart serve with harness integrations enabled before opening this connection.", {})
            # Always use the serve owner; no transport can promote this limited
            # principal into the operator used by the normal HTTP surface.
            session, _, reused, request_id = build_open_service(deps).open(context, **arguments)
            return {'agent_id': arguments['agent_id'], 'endpoint_id': arguments['endpoint_id'],
                'session_id': session.session_id, 'lifecycle_state': session.lifecycle_state, 'request_id': request_id, 'reused': reused}
        return await execute(run)

    return router
