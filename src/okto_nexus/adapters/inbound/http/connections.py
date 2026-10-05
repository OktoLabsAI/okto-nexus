"""Canonical connection discovery, execution policy and historical key revocation."""
import anyio
from fastapi import APIRouter, Request

from ....errors import OktoNexusError
from ..runtime_admin import RuntimeAdminBody


class ExecutionPolicyBody(RuntimeAdminBody):
    expected_revision: int
    execution_location: str
    local_adapter_id: str | None = None


class ConnectBody(RuntimeAdminBody):
    endpoint_id: str
    idempotency_key: str


def service(deps):
    from ..mcp.tools.harness import build_connection_service
    return build_connection_service(deps)


def build_router():
    from ..mcp.tools.harness import request_context
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

    @router.get('/agents/{agent_id}/execution-policy')
    async def execution_policy(request: Request, agent_id: str):
        from ....application.agent_execution_policy import read_policy
        return await execute(lambda: read_policy(request.app.state.deps, request_context(), agent_id))

    @router.get('/runtime-policy')
    async def global_runtime_policy(request: Request):
        from ....application.runtime_policy import read_policy
        return await execute(lambda: read_policy(request.app.state.deps, request_context()))

    @router.put('/runtime-policy')
    async def update_global_runtime_policy(request: Request, body: dict):
        from ....application.runtime_policy import save_policy
        return await execute(lambda: save_policy(request.app.state.deps, request_context(), changes=body))

    @router.get('/agents/{agent_id}/runtime-policy')
    async def agent_runtime_policy(request: Request, agent_id: str):
        from ....application.runtime_policy import read_policy
        return await execute(lambda: read_policy(request.app.state.deps, request_context(), agent_id))

    @router.get('/agents/{agent_id}/runtime-sessions')
    async def agent_runtime_sessions(request: Request, agent_id: str, workspace: str | None = None):
        from ....application.execution_session_views import agent_session_summary
        return await execute(lambda: agent_session_summary(request.app.state.deps, request_context(), agent_id, workspace))

    @router.put('/agents/{agent_id}/runtime-policy')
    async def update_agent_runtime_policy(request: Request, agent_id: str, body: dict):
        from ....application.runtime_policy import save_policy
        return await execute(lambda: save_policy(request.app.state.deps, request_context(), agent_id=agent_id, changes=body))

    @router.put('/agents/{agent_id}/execution-policy')
    async def update_execution_policy(request: Request, agent_id: str, body: ExecutionPolicyBody):
        from ....application.agent_execution_policy import save_policy
        return await execute(lambda: save_policy(request.app.state.deps, request_context(), agent_id, **body.model_dump()))

    @router.post('/connections/connect')
    async def connect(request: Request, body: ConnectBody):
        from ..mcp.tools.harness import connect_own_endpoint
        return await execute(lambda: connect_own_endpoint(request.app.state.deps, **body.model_dump()))

    @router.get('/agents/{agent_id}/connections')
    async def view(request: Request, agent_id: str):
        return await execute(lambda: service(request.app.state.deps).view(request_context(), agent_id=agent_id))

    @router.delete('/agents/{agent_id}/connection-keys/{key_id}')
    async def revoke(request: Request, agent_id: str, key_id: str):
        return await execute(lambda: service(request.app.state.deps).revoke(request_context(), agent_id=agent_id, key_id=key_id))


    return router
