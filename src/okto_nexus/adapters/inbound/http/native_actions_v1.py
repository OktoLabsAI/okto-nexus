"""Bearer-only native domain actions; never a canonical-key or MCP fallback."""

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from nexus_connector_core.protocol import strict_json

from ....application.execution_capabilities import ExecutionCapabilityService
from ....application.execution_native_actions import MAX_NATIVE_BYTES
from ....bootstrap.execution_authority import build_execution_access, build_native_action_service
from ....errors import OktoNexusError
from .app import extract_bearer, v1_err


def error_response(status, code, message, *, action_id=None, possible_effect=False):
    response = v1_err(status, code, message, stage='native_action')
    if possible_effect:
        response = JSONResponse({'error': {
            'code': code, 'stage': 'native_action', 'message': message,
            'possible_effect': True, 'retry_safe': False, 'operation_id': action_id,
            'action': 'Replay the same action ID and payload after recovering the connection.',
        }}, status_code=status)
    response.headers['Cache-Control'] = 'no-store'
    return response


def build_router():
    router = APIRouter()

    @router.post('/runtime/native-actions')
    async def native_action(request: Request):
        token = extract_bearer(request)
        if not token or not token.startswith('nxc4_'):
            return error_response(401, 'AUTH_FAILED', 'A native session capability is required.')
        deps = request.app.state.deps
        capabilities = ExecutionCapabilityService(factory=deps.connection_factory,
                                                   access=build_execution_access(deps))
        try:
            principal = await anyio.to_thread.run_sync(lambda: capabilities.authenticate_transport(
                token=token, audience='nexus-native-session'))
        except OktoNexusError:
            return error_response(401, 'AUTH_FAILED', 'The native session capability is invalid or inactive.')
        length = request.headers.get('content-length')
        if length is not None and (not length.isdecimal() or int(length) > MAX_NATIVE_BYTES):
            return error_response(413, 'CAPACITY_EXCEEDED', 'The native action body is too large.')
        parts, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_NATIVE_BYTES:
                return error_response(413, 'CAPACITY_EXCEEDED', 'The native action body is too large.')
            parts.append(chunk)
        try:
            body = strict_json(b''.join(parts).decode('utf-8', errors='strict'))
        except (ValueError, UnicodeError, RecursionError):
            return error_response(400, 'VALIDATION_ERROR', 'The native action body is invalid JSON.')
        service = build_native_action_service(deps)
        try:
            response = await anyio.to_thread.run_sync(lambda: service.invoke(principal=principal, body=body))
        except OktoNexusError as error:
            status = {'VALIDATION_ERROR': 422, 'CAPACITY_EXCEEDED': 413,
                      'PERMISSION_DENIED': 403, 'NOT_OWNER': 403, 'NOT_ELIGIBLE_TO_CLAIM': 403,
                      'APPROVAL_AUTHORITY_REQUIRED': 403,
                      'NOT_FOUND': 404, 'WORKSPACE_MISMATCH': 404,
                      'CONFLICT': 409, 'HANDOFF_ALREADY_CLAIMED': 409,
                      'INVALID_TRANSITION': 409, 'DEPENDENCY_NOT_MET': 409}.get(error.code, 500)
            if status < 500:
                return error_response(status, error.code, error.message)
            return error_response(503, 'OUTCOME_UNKNOWN', 'The native action outcome could not be confirmed.',
                                  action_id=body.get('action_id'), possible_effect=True)
        except Exception:
            return error_response(503, 'OUTCOME_UNKNOWN', 'The native action outcome could not be confirmed.',
                action_id=body.get('action_id') if isinstance(body, dict) else None, possible_effect=True)
        return JSONResponse(response, headers={'Cache-Control': 'no-store'})

    return router
