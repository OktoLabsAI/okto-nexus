"""Operator remote setup in the existing Connections HTTP family."""
import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ....application.remote_setup import RemoteSetupService
from ....application.remote_setup_contract import MAX_BYTES, ContractError, parse_document
from ....bootstrap.execution_authority import build_execution_access
from ....errors import OktoNexusError
from .identity_ctx import runtime_request_context


def build_router(runtime_error):
    router = APIRouter()

    async def run(request, method):
        try:
            data = bytearray()
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_BYTES:
                    raise ContractError()
                data.extend(chunk)
            body = parse_document(bytes(data))
            deps = request.app.state.deps
            service = RemoteSetupService(deps=deps, access=build_execution_access(deps),
                settings=request.app.state.settings_service)
            context = runtime_request_context()
            result = await anyio.to_thread.run_sync(lambda: getattr(service, method)(context, body))
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except OktoNexusError as error:
            return runtime_error(error, 'remote_setup.' + method)

    @router.post('/connections/remote-setup:review')
    async def remote_setup_review(request: Request):
        return await run(request, 'review')

    @router.post('/connections/remote-setup:bootstrap')
    async def remote_setup_bootstrap(request: Request):
        return await run(request, 'bootstrap')

    @router.post('/connections/remote-setup:recover')
    async def remote_setup_recover(request: Request):
        return await run(request, 'recover')

    @router.post('/connections/remote-setup:materialization')
    async def remote_setup_materialization(request: Request):
        return await run(request, 'materialization')

    return router
