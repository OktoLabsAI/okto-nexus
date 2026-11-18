"""Local operator transport for a scoped Codex presenter."""

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from ipaddress import ip_address
from typing import Annotated, Literal

import anyio
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from nexus_connector_core import CoreError, NativeSessionOwnerProof
from nexus_connector_core.protocol import canonical_json, strict_json
from pydantic import Field

from ....application.codex_presenter_channel import CodexPresenterHistoryChannel
from ....application.execution_native_session_mapping import ManagedNativeSession
from ....application.session_attachment_broker import SessionAttachmentBroker
from ....domain.session_interaction import InputAuthor, InputScope
from ....errors import OktoNexusError
from .dashboard_session_input import _HEADERS, _error, _runtime_error
from .executor_link import _safe_transport
from .operator_auth import COOKIE, same_origin_request
from .session_interaction_contract import (
    Identifier,
    PrepareAttachment,
    Revision,
    ScopedSession,
    _Document,
)

_AUDIENCE = 'nexus.local.codex.v1'
_SUBPROTOCOL = 'nexus.presenter.v1'
_MAX_REQUEST_BYTES = 64 * 1024
_MAX_RESPONSE_BYTES = 512 * 1024
_RENEW_SECONDS = 15


@dataclass(frozen=True, slots=True)
class LocalCodexPresentations:
    """Available only when the Server has installed an eligible owner and capability."""

    broker: SessionAttachmentBroker
    prove_owner: Callable[[InputScope], Awaitable[tuple[ManagedNativeSession, NativeSessionOwnerProof]]]
    execution_access: object


class _Hello(ScopedSession):
    kind: Literal['hello']
    version: Literal[1]


class _ChallengeReply(_Document):
    kind: Literal['prove']
    challenge: Identifier


class _HistoryRequest(_Document):
    kind: Literal['page']
    request_id: Revision
    method: Literal['thread/turns/list', 'thread/items/list']
    params: Annotated[dict, Field(max_length=8)]


class _Detach(ScopedSession):
    channel_id: Identifier


def _local_transport(request) -> bool:
    if not request.client or any(name in request.headers for name in (
            'forwarded', 'x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto')):
        return False
    try:
        hostname = request.url.hostname
        local_host = hostname == 'localhost' or (hostname is not None and ip_address(hostname).is_loopback)
        return bool(local_host and ip_address(request.client.host).is_loopback)
    except ValueError:
        return False


def _upgrade_allowed(ws: WebSocket) -> bool:
    if (not _local_transport(ws) or ws.query_params or ws.headers.get('sec-fetch-site') == 'cross-site'
            or len(ws.headers.getlist('origin')) > 1
            or _SUBPROTOCOL not in ws.scope.get('subprotocols', ())):
        return False
    try:
        return _safe_transport(ws)
    except ValueError:
        return False


def _ticket(ws: WebSocket) -> str | None:
    values = ws.headers.getlist('authorization')
    if len(values) != 1 or not values[0].startswith('Bearer '):
        return None
    token = values[0][7:]
    return token if len(token) == 43 and token.isascii() and all(
        character.isalnum() or character in '-_' for character in token) else None


async def _worker(function, **arguments):
    return await anyio.to_thread.run_sync(partial(function, **arguments))


async def _receive(ws: WebSocket):
    message = await ws.receive()
    if message['type'] == 'websocket.disconnect':
        raise WebSocketDisconnect(message.get('code', 1000))
    wire = message.get('text')
    if not isinstance(wire, str) or len(wire) > _MAX_REQUEST_BYTES or len(wire.encode()) > _MAX_REQUEST_BYTES:
        raise ValueError('Invalid presentation frame')
    return strict_json(wire)


async def _send(ws: WebSocket, frame):
    raw = canonical_json(frame)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError('Presentation frame too large')
    with anyio.fail_after(5):
        await ws.send_text(raw.decode())


def _services(state):
    return getattr(state, 'local_codex_presentations', None)


async def _present(ws, services, author, attachment_id, ticket):
    broker = services.broker
    channel_id = 'viewer_' + secrets.token_hex(16)
    scope = None
    await ws.accept(subprotocol=_SUBPROTOCOL)
    try:
        with anyio.fail_after(10):
            hello = _Hello.model_validate(await _receive(ws))
            scope = hello.input_scope()
            if _services(ws.app.state) is not services:
                raise ValueError('Presentation owner changed')
            credentials = {'scope': scope, 'author': author, 'attachment_id': attachment_id,
                           'audience': _AUDIENCE, 'channel_id': channel_id, 'ticket': ticket}
            nonce = await _worker(broker.challenge, **credentials)
            await _send(ws, {'kind': 'challenge', 'challenge': nonce, 'channel_id': channel_id})
            proof = _ChallengeReply.model_validate(await _receive(ws))
            if _services(ws.app.state) is not services:
                raise ValueError('Presentation owner changed')
            attachment = await _worker(broker.attach, **credentials, challenge=proof.challenge)
            active = {'scope': scope, 'author': author, 'attachment': attachment,
                      'audience': _AUDIENCE, 'channel_id': channel_id}
            await _send(ws, {'kind': 'attached', 'attachment_id': attachment_id, 'access': attachment.access})
        history = CodexPresenterHistoryChannel(broker=broker, prove_owner=services.prove_owner,
                                              access=services.execution_access, **active)
        next_renewal = anyio.current_time() + _RENEW_SECONDS
        while _services(ws.app.state) is services:
            with anyio.move_on_after(max(0, next_renewal - anyio.current_time())) as deadline:
                raw = await _receive(ws)
            if deadline.cancel_called:
                await _worker(broker.refresh, **active)
                next_renewal = anyio.current_time() + _RENEW_SECONDS
                continue
            request = _HistoryRequest.model_validate(raw)
            page = await history.page(method=request.method, params=request.params)
            if _services(ws.app.state) is not services:
                break
            await _send(ws, {'kind': 'page', 'request_id': request.request_id, 'page': page})
        await ws.close(code=4409)
    except WebSocketDisconnect:
        return
    except (CoreError, OktoNexusError, ValueError, RecursionError, TimeoutError):
        await ws.close(code=4409)
    finally:
        if scope is not None:
            with anyio.CancelScope(shield=True):
                await _worker(broker.disconnect, scope=scope, attachment_id=attachment_id, channel_id=channel_id)


def build_router():
    router = APIRouter()

    @router.post('/sessions/{session_id}/attachments:prepare')
    async def prepare(session_id: str, body: PrepareAttachment, request: Request):
        if not _local_transport(request) or not same_origin_request(request):
            return _error(403, 'PERMISSION_DENIED', 'Local operator access is required.')
        if session_id != body.scope.session_id or request.query_params:
            return _error(422, 'VALIDATION_ERROR', 'An exact presentation scope is required.')
        state = request.app.state
        token = request.cookies.get(COOKIE)
        if await _worker(state.operator_auth.resolve, token=token) is None:
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to prepare this presentation.')
        services = _services(state)
        if services is None or body.intent != 'attach_live' or body.access != 'read':
            return _error(409, 'CONFLICT', 'This local presentation is currently unavailable.')
        scope = body.input_scope()
        try:
            mapping, _ = await services.prove_owner(scope)
            if mapping.codex_thread_id is None or _services(state) is not services:
                raise CoreError('SESSION_CONFLICT', 'native_presentation')
            reference = await _worker(state.operator_auth.authority_reference, token=token)
            if reference is None:
                return _error(401, 'AUTH_FAILED', 'The operator login has expired.')
            offer = await _worker(services.broker.prepare, scope=scope, author=InputAuthor(reference, 'native_terminal'),
                audience=_AUDIENCE, capability_revision=body.capability_revision, client_intent_id=body.client_intent_id,
                access=body.access)
        except OktoNexusError as error:
            return _runtime_error(error)
        except CoreError:
            return _error(409, 'CONFLICT', 'This local presentation is currently unavailable.')
        return JSONResponse({'version': 1, 'attachment_id': offer.attachment_id, 'state': offer.state,
                             'ticket': offer.ticket}, status_code=201 if offer.ticket else 200, headers=_HEADERS)

    @router.websocket('/attachments/{attachment_id}/stream')
    async def stream(ws: WebSocket, attachment_id: str):
        services, ticket = _services(ws.app.state), _ticket(ws)
        if services is None or ticket is None or not _upgrade_allowed(ws):
            await ws.close(code=4403)
            return
        reference = await _worker(ws.app.state.operator_auth.authority_reference,
                                  token=ws.cookies.get(COOKIE), create=False)
        if reference is None:
            await ws.close(code=4401)
            return
        await _present(ws, services, InputAuthor(reference, 'native_terminal'), attachment_id, ticket)

    @router.post('/attachments/{attachment_id}/detach')
    async def detach(attachment_id: str, body: _Detach, request: Request):
        if not _local_transport(request) or not same_origin_request(request) or request.query_params:
            return _error(403, 'PERMISSION_DENIED', 'Local operator access is required.')
        state = request.app.state
        reference = await _worker(state.operator_auth.authority_reference, token=request.cookies.get(COOKIE), create=False)
        if reference is None:
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to detach this presentation.')
        services = _services(state)
        if services is None:
            return _error(409, 'CONFLICT', 'This local presentation is currently unavailable.')
        try:
            await _worker(services.broker.detach, scope=body.input_scope(), channel_id=body.channel_id,
                          author=InputAuthor(reference, 'native_terminal'), attachment_id=attachment_id)
        except OktoNexusError as error:
            return _runtime_error(error)
        return JSONResponse({'version': 1, 'state': 'DETACHED'}, headers=_HEADERS)

    return router
