"""Local operator lifecycle facts; no new public or remote control authority."""
from __future__ import annotations

from importlib.metadata import version
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ....application.service_lifecycle import project_server_readiness
from ....errors import OktoNexusError
from ...outbound.service_manager.identity import server_instance_id
from .routes import _map_error, _require_operator


class StopServiceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    instance_id: str = Field(min_length=1, max_length=100)
    generation: str = Field(min_length=1, max_length=100)
    timeout_seconds: float = Field(default=30.0, ge=0, le=300, allow_inf_nan=False)
    force: bool = False


def build_router(lock) -> APIRouter:
    router = APIRouter()
    # Capture the active package at startup. Reading distribution metadata on
    # each request could advertise an upgraded on-disk version for an old daemon.
    active_version = version('okto-nexus')
    identity = server_instance_id(lock.home_dir, lock.db_path) if lock is not None else None

    def authorize(request):
        if request.client is None or request.client.host not in {'127.0.0.1', '::1'}:
            return JSONResponse({'ok': False, 'error': {'code': 'PERMISSION_DENIED',
                'message': 'Service lifecycle inspection requires the local operator channel.'}}, status_code=403)
        try:
            _require_operator()
        except OktoNexusError as error:
            return _map_error(error)
        if lock is None or identity is None:
            return JSONResponse({'ok': False, 'error': {'code': 'SERVICE_IDENTITY_UNAVAILABLE',
                'message': 'This application has no foreground service owner.'}}, status_code=503)
        return None

    @router.get('/service')
    async def inspect_service(request: Request):
        denied = authorize(request)
        if denied is not None:
            return denied
        owner = getattr(request.app.state, 'runtime_shutdown', None)
        state = owner.status()['state'] if owner is not None else 'RUNNING'
        result = project_server_readiness(identity=identity, generation=lock.generation or '',
            version=active_version, pid=os.getpid(), owns_instance=lock.owned,
            startup_complete=owner is not None,
            admission_closed=request.app.state.deps.runtime_admission_fence.closed,
            shutdown_state=state,
            supervisor=getattr(request.app.state, 'service_supervisor', 'foreground'))
        data = result.to_dict()
        if owner is not None and state != 'RUNNING':
            data['shutdown'] = owner.status()
        return JSONResponse({'ok': True, 'data': data}, headers={'Cache-Control': 'no-store'})

    @router.post('/service/stop')
    async def stop_service(body: StopServiceRequest, request: Request):
        denied = authorize(request)
        if denied is not None:
            return denied
        if not lock.owned or body.instance_id != identity or body.generation != lock.generation:
            return JSONResponse({'ok': False, 'error': {'code': 'INSTANCE_MISMATCH',
                'message': 'Inspect the current instance before requesting shutdown.'}}, status_code=409)
        owner = getattr(request.app.state, 'runtime_shutdown', None)
        if owner is None:
            return JSONResponse({'ok': False, 'error': {'code': 'RECONCILIATION_REQUIRED',
                'message': 'The shutdown coordinator is not available.'}}, status_code=503)
        # Same canonical coordinator used by /v1/runtime/shutdown. This local
        # operator adapter neither grants participant authority nor signals PIDs.
        try:
            report = await owner.request(timeout_seconds=body.timeout_seconds, force=body.force)
        except OktoNexusError as error:
            return _map_error(error)
        return JSONResponse({'ok': True, 'data': {'instance_id': identity,
            'generation': lock.generation, 'shutdown': report}},
            status_code=200 if report['state'] == 'DRAINED' else 202,
            headers={'Cache-Control': 'no-store'})

    return router
