"""Local operator lifecycle facts; no new public or remote control authority."""
from __future__ import annotations

from importlib.metadata import version
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ....application.service_lifecycle import project_server_readiness
from ....errors import OktoNexusError
from ...outbound.service_manager.identity import server_instance_id
from .routes import _map_error, _require_operator


def build_router(lock) -> APIRouter:
    router = APIRouter()
    # Capture the active package at startup. Reading distribution metadata on
    # each request could advertise an upgraded on-disk version for an old daemon.
    active_version = version('okto-nexus')
    identity = server_instance_id(lock.home_dir, lock.db_path) if lock is not None else None

    @router.get('/service')
    async def inspect_service(request: Request):
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
        owner = getattr(request.app.state, 'runtime_shutdown', None)
        state = owner.status()['state'] if owner is not None else 'RUNNING'
        result = project_server_readiness(identity=identity, generation=lock.generation or '',
            version=active_version, pid=os.getpid(), owns_instance=lock.owned,
            startup_complete=owner is not None,
            admission_closed=request.app.state.deps.runtime_admission_fence.closed,
            shutdown_state=state)
        return JSONResponse({'ok': True, 'data': result.to_dict()}, headers={'Cache-Control': 'no-store'})

    return router
