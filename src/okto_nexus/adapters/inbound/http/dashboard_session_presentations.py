"""Local operator transport for scoped native presenters."""

import asyncio
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from dataclasses import dataclass, field
from functools import partial
from ipaddress import ip_address
from typing import Annotated, Literal
from weakref import WeakValueDictionary

import anyio
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from nexus_connector_core import CoreError, NativeSessionOwnerProof
from nexus_connector_core.protocol import canonical_json, strict_json
from pydantic import Field, TypeAdapter

from ....adapters.outbound.execution.core_inventory import protocol_info
from ....application.codex_presenter_channel import CodexPresenterHistoryChannel
from ....application.codex_viewer_protocol import CodexViewerContext
from ....application.execution_native_session_mapping import ManagedNativeSession
from ....application.session_attachment_broker import SessionAttachmentBroker
from ....application.session_interaction_authority import enqueue_human_input
from ....application.session_interaction_controls import request_exact_human_interrupt
from ....application.session_interaction_promotion import steer_human_input
from ....domain.presentation_protocol import (
    LOCAL_CODEX_AUDIENCE,
    LOCAL_PI_AUDIENCE,
    MAX_PI_PRESENTATION_BYTES,
    MAX_PRESENTATION_REQUEST_BYTES,
    MAX_PRESENTATION_RESPONSE_BYTES,
    PRESENTATION_SUBPROTOCOL,
    PI_PRESENTATION_SUBPROTOCOL,
)
from ....domain.session_interaction import InputAuthor, InputScope
from ....errors import ErrorCode, OktoNexusError
from .dashboard_session_input import (
    _HEADERS,
    _error,
    _interrupt_target_for,
    _runtime_error,
    review_exact_interrupt,
)
from .dashboard_session_steer import review_exact_steer
from .executor_link import _safe_transport
from .operator_auth import COOKIE, same_origin_request
from .session_interaction_contract import (
    Identifier,
    InterruptTargetView,
    PrepareAttachment,
    Revision,
    ScopedSession,
    SteerTargetView,
    TextInput,
    _Document,
)

_AUDIENCE = LOCAL_CODEX_AUDIENCE
_RENEW_SECONDS = 15


@dataclass(frozen=True, slots=True)
class LocalCodexPresentations:
    """Available only when the Server has installed an eligible owner and capability."""

    broker: SessionAttachmentBroker
    prove_owner: Callable[[InputScope], Awaitable[tuple[ManagedNativeSession, NativeSessionOwnerProof]]]
    execution_access: object
    read_context: Callable[[InputScope], Awaitable[CodexViewerContext | None]] | None = None
    live_updates: bool = False
    next_turn_revision: Callable[[object, InputScope], str | None] | None = None


@dataclass(frozen=True, slots=True)
class LocalPiPresentations:
    broker: SessionAttachmentBroker
    prove_owner: Callable[[InputScope], Awaitable[tuple[ManagedNativeSession, NativeSessionOwnerProof]]]
    open_renderer: Callable[..., AbstractAsyncContextManager[AsyncIterator[bytes]]]
    execution_access: object | None = None
    next_turn_revision: Callable[[object, InputScope], str | None] | None = None
    renderer_locks: WeakValueDictionary[InputScope, asyncio.Lock] = field(default_factory=WeakValueDictionary,
                                                                          repr=False, compare=False)


class _Hello(ScopedSession):
    kind: Literal['hello']
    version: Literal[1]


class _PiHello(_Hello):
    columns: Annotated[int, Field(strict=True, ge=24, le=300)]
    rows: Annotated[int, Field(strict=True, ge=8, le=120)]


class _ChallengeReply(_Document):
    kind: Literal['prove']
    challenge: Identifier


class _HistoryRequest(_Document):
    kind: Literal['page']
    request_id: Revision
    method: Literal['thread/turns/list', 'thread/items/list']
    params: Annotated[dict, Field(max_length=8)]


class _ContextRequest(_Document):
    kind: Literal['context']
    request_id: Revision
    follow: Literal[True] | None = None


class _UpdatesRequest(_Document):
    kind: Literal['updates']
    request_id: Revision


class _PiEnqueueRequest(_Document):
    kind: Literal['enqueue']
    request_id: Revision
    client_intent_id: Identifier
    capability_revision: Identifier
    content: TextInput


class _EnqueueRequest(_PiEnqueueRequest):
    thread_id: Identifier


class _InputDeliveryRequest(_Document):
    kind: Literal['input_delivery']
    request_id: Revision
    input_id: Identifier


class _TurnReviewRequest(_Document):
    request_id: Revision
    thread_id: Identifier
    turn_id: Identifier
    client_intent_id: Identifier


class _SteerReviewRequest(_TurnReviewRequest):
    kind: Literal['steer_review']
    content: TextInput


class _InterruptReviewRequest(_TurnReviewRequest):
    kind: Literal['interrupt_review']


class _TurnConfirmRequest(_Document):
    kind: Literal['steer_confirm', 'interrupt_confirm']
    request_id: Revision
    review_id: Identifier


class _InterruptReceiptRequest(_Document):
    kind: Literal['interrupt_receipt']
    request_id: Revision
    thread_id: Identifier
    client_intent_id: Identifier


@dataclass(frozen=True, slots=True)
class _ReviewedTurn:
    id: str
    expires: float
    request: _SteerReviewRequest | _InterruptReviewRequest
    target: SteerTargetView | InterruptTargetView


_REQUEST = TypeAdapter(Annotated[_HistoryRequest | _ContextRequest | _UpdatesRequest | _EnqueueRequest
                                 | _InputDeliveryRequest | _SteerReviewRequest | _InterruptReviewRequest
                                 | _TurnConfirmRequest | _InterruptReceiptRequest,
                                 Field(discriminator='kind')])


class _Review(ScopedSession):
    access: Literal['read', 'write'] = 'read'
    presentation: Literal['codex', 'pi'] = 'codex'


class _Detach(ScopedSession):
    channel_id: Identifier
    presentation: Literal['codex', 'pi'] = 'codex'


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


def _upgrade_allowed(ws: WebSocket, protocol=PRESENTATION_SUBPROTOCOL) -> bool:
    if (not _local_transport(ws) or ws.query_params or ws.headers.get('sec-fetch-site') == 'cross-site'
            or len(ws.headers.getlist('origin')) > 1
            or protocol not in ws.scope.get('subprotocols', ())):
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
    return _decode(await ws.receive())


def _decode(message):
    if message['type'] == 'websocket.disconnect':
        raise WebSocketDisconnect(message.get('code', 1000))
    wire = message.get('text')
    if (not isinstance(wire, str) or len(wire) > MAX_PRESENTATION_REQUEST_BYTES
            or len(wire.encode()) > MAX_PRESENTATION_REQUEST_BYTES):
        raise ValueError('Invalid presentation frame')
    return strict_json(wire)


async def _send(ws: WebSocket, frame):
    raw = canonical_json(frame)
    if len(raw) > MAX_PRESENTATION_RESPONSE_BYTES:
        raise ValueError('Presentation frame too large')
    with anyio.fail_after(5):
        await ws.send_text(raw.decode())


def _services(state, presentation='codex'):
    return getattr(state, 'local_pi_presentations' if presentation == 'pi' else 'local_codex_presentations', None)


def _matching_presenter(mapping, *, pi: bool) -> bool:
    return mapping.adapter_id == 'pi_rpc' if pi else mapping.codex_thread_id is not None


def _verify_writer(state, services, active, uow, human, *, presentation='codex'):
    if _services(state, presentation) is not services:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The presentation owner changed.', {})
    services.broker.require_writer_effect(uow, human, **active)


async def _review_turn(state, services, active, history, request):
    if active['attachment'].access != 'write' or services.next_turn_revision is None:
        return None
    await history.verify_input_thread(request.thread_id)

    def read():
        with services.broker.factory.unit_of_work(write=False) as uow:
            if isinstance(request, _SteerReviewRequest):
                return review_exact_steer(uow, active['scope'], services.next_turn_revision)
            return review_exact_interrupt(uow, active['scope'], _interrupt_target_for(state))

    target = await _worker(read)
    if target is None or target.target.turn_id != request.turn_id:
        return None
    return _ReviewedTurn(secrets.token_urlsafe(24), time.monotonic() + 45, request, target)


async def _confirm_turn(state, services, active, history, review, request):
    if (review is None or request.review_id != review.id or time.monotonic() >= review.expires
            or (request.kind == 'steer_confirm') != isinstance(review.request, _SteerReviewRequest)):
        return {'status': 'refused'}
    await history.verify_input_thread(review.request.thread_id)

    def cut(uow, human):
        if time.monotonic() >= review.expires:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The turn review expired.', {})
        _verify_writer(state, services, active, uow, human)

    common = {'factory': services.broker.factory, 'access': services.execution_access,
        'authority_fence': services.broker.authority_fence, 'scope': active['scope'], 'author': active['author'],
        'client_intent_id': review.request.client_intent_id, 'native_turn_id': review.request.turn_id,
        'capability_revision': review.target.capability_revision, 'expected_queue_revision': review.target.queue_revision,
        'fresh_publications': state.inventory_fresh_publications, 'remote_ready': protocol_info()['remote_execution_ready'],
        'verify_presenter': cut}
    try:
        if isinstance(review.request, _InterruptReviewRequest):
            target_for = _interrupt_target_for(state)
            if target_for is None:
                return {'status': 'refused'}
            await _worker(request_exact_human_interrupt, current_interrupt_target=target_for, **common)
            return {'status': 'recorded'}
        revisions = getattr(state, 'session_input_dispatch_options', {}).get('session_steer_revisions')
        if revisions is None or not isinstance(review.target, SteerTargetView):
            return {'status': 'refused'}
        receipt = await _worker(steer_human_input, current_steer_revisions=revisions,
            confirmed_effect_revision=review.target.effect_revision, text=review.request.content.text, **common)
    except OktoNexusError as error:
        if error.code in (ErrorCode.CONFLICT, ErrorCode.PERMISSION_DENIED, ErrorCode.VALIDATION_ERROR, ErrorCode.NOT_FOUND):
            return {'status': 'refused'}
        raise
    return {'status': 'recorded', 'input_id': receipt.input_id}


async def _enqueue(state, services, active, history, request):
    if active['attachment'].access != 'write' or services.next_turn_revision is None:
        raise ValueError('This presentation cannot enqueue input')
    await history.verify_input_thread(request.thread_id)
    return await _record_presenter_input(state, services, active, request, presentation='codex')


async def _record_presenter_input(state, services, active, request, *, presentation):
    broker = services.broker

    def verify_presenter(uow, human):
        _verify_writer(state, services, active, uow, human, presentation=presentation)

    receipt = await _worker(enqueue_human_input, factory=broker.factory, access=services.execution_access,
        authority_fence=broker.authority_fence, current_capability_revision=services.next_turn_revision,
        scope=active['scope'], author=active['author'], client_intent_id=request.client_intent_id,
        capability_revision=request.capability_revision, text=request.content.text, verify_presenter=verify_presenter)
    return {'kind': 'enqueue', 'input_id': receipt.input_id, 'enqueue_sequence': receipt.sequence,
            'status': receipt.status, 'operation_id': receipt.operation_id, 'possible_effect': receipt.possible_effect}


async def _present_pi(ws, services, active, hello):
    access = active['attachment'].access
    state = ws.app.state

    async def verify(*, renew=False):
        if _services(state, 'pi') is not services:
            raise ValueError('Presentation owner changed')
        await _worker(services.broker.refresh if renew else services.broker.require_active, **active)
        if _services(state, 'pi') is not services:
            raise ValueError('Presentation owner changed')

    async with AsyncExitStack() as stack:
        with anyio.fail_after(10):
            # A replaced writer retires on its next broker check before the
            # next viewer opens the single renderer slot.
            lock = services.renderer_locks.setdefault(active['scope'], asyncio.Lock())
            await stack.enter_async_context(lock)
            await verify()
            frames = await stack.enter_async_context(services.open_renderer(
                active['scope'], columns=hello.columns, rows=hello.rows))
            await verify()
            await _send(ws, {'kind': 'attached', 'attachment_id': active['attachment'].attachment_id, 'access': access})

        inbound = asyncio.create_task(ws.receive())
        output = asyncio.ensure_future(anext(frames, None))
        renewal = anyio.current_time() + _RENEW_SECONDS
        try:
            while True:
                done, _ = await asyncio.wait((inbound, output), timeout=1, return_when=asyncio.FIRST_COMPLETED)
                message = None
                if inbound in done:
                    message = inbound.result()
                    if message['type'] == 'websocket.disconnect':
                        return
                renew = anyio.current_time() >= renewal
                await verify(renew=renew)
                if renew:
                    renewal = anyio.current_time() + _RENEW_SECONDS
                if message is not None:
                    if access != 'write' or services.next_turn_revision is None:
                        raise ValueError('This presentation cannot enqueue input')
                    request = _PiEnqueueRequest.model_validate(_decode(message))
                    reply = await _record_presenter_input(state, services, active, request, presentation='pi')
                    if _services(state, 'pi') is not services:
                        break
                    await _send(ws, {'request_id': request.request_id, **reply})
                    inbound = asyncio.create_task(ws.receive())
                if output not in done:
                    continue
                data = output.result()
                if data is None:
                    break
                if type(data) is not bytes or not 1 <= len(data) <= MAX_PI_PRESENTATION_BYTES:
                    raise ValueError('Invalid renderer frame')
                with anyio.fail_after(5):
                    await ws.send_bytes(data)
                output = asyncio.ensure_future(anext(frames, None))
        finally:
            inbound.cancel()
            output.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.gather(inbound, output, return_exceptions=True)
    await ws.close(code=4409)


async def _present(ws, services, author, attachment_id, ticket, presentation):
    broker = services.broker
    pi = presentation == 'pi'
    audience = LOCAL_PI_AUDIENCE if pi else _AUDIENCE
    channel_id = 'viewer_' + secrets.token_hex(16)
    scope = None
    await ws.accept(subprotocol=PI_PRESENTATION_SUBPROTOCOL if pi else PRESENTATION_SUBPROTOCOL)
    try:
        with anyio.fail_after(10):
            hello = (_PiHello if pi else _Hello).model_validate(await _receive(ws))
            scope = hello.input_scope()
            if _services(ws.app.state, presentation) is not services:
                raise ValueError('Presentation owner changed')
            credentials = {'scope': scope, 'author': author, 'attachment_id': attachment_id,
                           'audience': audience, 'channel_id': channel_id, 'ticket': ticket}
            nonce = await _worker(broker.challenge, **credentials)
            await _send(ws, {'kind': 'challenge', 'challenge': nonce, 'channel_id': channel_id})
            proof = _ChallengeReply.model_validate(await _receive(ws))
            if _services(ws.app.state, presentation) is not services:
                raise ValueError('Presentation owner changed')
            attachment = await _worker(broker.attach, **credentials, challenge=proof.challenge)
            active = {'scope': scope, 'author': author, 'attachment': attachment,
                      'audience': audience, 'channel_id': channel_id}
            if not pi:
                await _send(ws, {'kind': 'attached', 'attachment_id': attachment_id, 'access': attachment.access})
        if pi:
            await _present_pi(ws, services, active, hello)
            return
        history = CodexPresenterHistoryChannel(broker=broker, prove_owner=services.prove_owner,
                                              access=services.execution_access, **active)
        next_renewal = anyio.current_time() + _RENEW_SECONDS
        reviewed = None
        while _services(ws.app.state) is services:
            with anyio.move_on_after(max(0, next_renewal - anyio.current_time())) as deadline:
                raw = await _receive(ws)
            if deadline.cancel_called:
                await _worker(broker.refresh, **active)
                next_renewal = anyio.current_time() + _RENEW_SECONDS
                continue
            request = _REQUEST.validate_python(raw)
            if isinstance(request, _ContextRequest):
                if services.read_context is None:
                    raise ValueError('Presentation context is unavailable')
                context = await history.viewer_context(services.read_context,
                    can_follow=services.live_updates and request.follow is True)
                reply = {'kind': 'context', 'context': context.model_dump(mode='json')}
            elif isinstance(request, _HistoryRequest):
                page = await history.page(method=request.method, params=request.params)
                reply = {'kind': 'page', 'page': page}
            elif isinstance(request, _EnqueueRequest):
                reply = await _enqueue(ws.app.state, services, active, history, request)
            elif isinstance(request, _InputDeliveryRequest):
                reply = {'kind': 'input_delivery', 'input_delivery': await history.input_delivery(request.input_id)}
            elif isinstance(request, _TurnReviewRequest):
                reviewed = await _review_turn(ws.app.state, services, active, history, request)
                control = {'review_id': reviewed.id, 'turn_id': request.turn_id} if reviewed else {}
                reply = {'kind': request.kind, request.kind: control}
            elif isinstance(request, _TurnConfirmRequest):
                review, reviewed = reviewed, None
                control = await _confirm_turn(ws.app.state, services, active, history, review, request)
                reply = {'kind': request.kind, request.kind: control}
            elif isinstance(request, _InterruptReceiptRequest):
                receipt = await history.interrupt_receipt(thread_id=request.thread_id, intent=request.client_intent_id,
                    current_interrupt_target=_interrupt_target_for(ws.app.state))
                reply = {'kind': 'interrupt_receipt', 'interrupt_receipt': receipt}
            else:
                if not services.live_updates:
                    raise ValueError('Presentation updates are unavailable')
                reply = {'kind': 'updates', 'updates': await history.updates()}
            if _services(ws.app.state) is not services:
                break
            await _send(ws, {'request_id': request.request_id, **reply})
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

    @router.post('/sessions/{session_id}/attachments:review')
    async def review(session_id: str, body: _Review, request: Request):
        if not _local_transport(request) or not same_origin_request(request):
            return _error(403, 'PERMISSION_DENIED', 'Local operator access is required.')
        if session_id != body.scope.session_id or request.query_params:
            return _error(422, 'VALIDATION_ERROR', 'An exact presentation scope is required.')
        state = request.app.state
        token = request.cookies.get(COOKIE)
        if await _worker(state.operator_auth.resolve, token=token) is None:
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to review this presentation.')
        pi = body.presentation == 'pi'
        services = _services(state, body.presentation)
        writing = body.access == 'write'
        if (services is None or writing and services.next_turn_revision is None
                or not pi and services.read_context is None):
            return _error(409, 'CONFLICT', 'This local presentation is currently unavailable.')
        scope = body.input_scope()
        try:
            mapping, _ = await services.prove_owner(scope)
            if not _matching_presenter(mapping, pi=pi) or _services(state, body.presentation) is not services:
                raise CoreError('SESSION_CONFLICT', 'native_presentation')
            reference = await _worker(state.operator_auth.authority_reference, token=token)
            if reference is None:
                return _error(401, 'AUTH_FAILED', 'The operator login has expired.')
            authority = {'scope': scope, 'author': InputAuthor(reference, 'native_terminal'),
                         'audience': LOCAL_PI_AUDIENCE if pi else _AUDIENCE}
            review_capability = services.broker.review_writer if writing else services.broker.review_reader
            reviewed = await _worker(review_capability, **authority)
            if not pi:
                context = await services.read_context(scope)
                if context is None or context.thread_id != mapping.codex_thread_id:
                    raise CoreError('SESSION_CONFLICT', 'native_presentation')
            if (reviewed != await _worker(review_capability, **authority)
                    or _services(state, body.presentation) is not services):
                raise CoreError('SESSION_CONFLICT', 'native_presentation')
            details = {'attach_strategy': 'pi_local_read' if pi else 'codex_local_read', 'capability_revision': reviewed}
            if writing:
                def input_revision():
                    with services.broker.factory.unit_of_work(write=False) as uow:
                        return services.next_turn_revision(uow, scope)

                revision = await _worker(input_revision)
                if revision is None or _services(state, body.presentation) is not services:
                    raise CoreError('SESSION_CONFLICT', 'native_presentation')
                details = {'attach_strategy': f'{body.presentation}_local_write', 'capability_revision': reviewed.capability_revision,
                    'writer_epoch': reviewed.epoch, 'writer_occupied': reviewed.occupied,
                    'input_capability_revision': revision}
        except OktoNexusError as error:
            return _runtime_error(error)
        except CoreError:
            return _error(409, 'CONFLICT', 'This local presentation is currently unavailable.')
        return JSONResponse({'version': 1, **details, **body.model_dump(exclude={'access', 'presentation'})}, headers=_HEADERS)

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
        pi = body.presentation == 'pi'
        services = _services(state, body.presentation)
        if (services is None or body.intent != 'attach_live'
                or body.access == 'write' and services.next_turn_revision is None):
            return _error(409, 'CONFLICT', 'This local presentation is currently unavailable.')
        scope = body.input_scope()
        try:
            mapping, _ = await services.prove_owner(scope)
            if not _matching_presenter(mapping, pi=pi) or _services(state, body.presentation) is not services:
                raise CoreError('SESSION_CONFLICT', 'native_presentation')
            reference = await _worker(state.operator_auth.authority_reference, token=token)
            if reference is None:
                return _error(401, 'AUTH_FAILED', 'The operator login has expired.')
            offer = await _worker(services.broker.prepare, scope=scope, author=InputAuthor(reference, 'native_terminal'),
                audience=LOCAL_PI_AUDIENCE if pi else _AUDIENCE,
                capability_revision=body.capability_revision, client_intent_id=body.client_intent_id,
                access=body.access, expected_writer_epoch=body.expected_writer_epoch, takeover=body.takeover)
        except OktoNexusError as error:
            return _runtime_error(error)
        except CoreError:
            return _error(409, 'CONFLICT', 'This local presentation is currently unavailable.')
        return JSONResponse({'version': 1, 'attachment_id': offer.attachment_id, 'state': offer.state,
                             'ticket': offer.ticket, 'live_updates': True if pi else services.live_updates},
                            status_code=201 if offer.ticket else 200, headers=_HEADERS)

    @router.websocket('/attachments/{attachment_id}/stream')
    async def stream(ws: WebSocket, attachment_id: str):
        offered = set(ws.scope.get('subprotocols', ()))
        recognized = offered & {PI_PRESENTATION_SUBPROTOCOL, PRESENTATION_SUBPROTOCOL}
        if len(recognized) != 1:
            await ws.close(code=4403)
            return
        protocol = recognized.pop()
        presentation = 'pi' if protocol == PI_PRESENTATION_SUBPROTOCOL else 'codex'
        services, ticket = _services(ws.app.state, presentation), _ticket(ws)
        if services is None or ticket is None or not _upgrade_allowed(ws, protocol):
            await ws.close(code=4403)
            return
        reference = await _worker(ws.app.state.operator_auth.authority_reference,
                                  token=ws.cookies.get(COOKIE), create=False)
        if reference is None:
            await ws.close(code=4401)
            return
        await _present(ws, services, InputAuthor(reference, 'native_terminal'), attachment_id, ticket, presentation)

    @router.post('/attachments/{attachment_id}/detach')
    async def detach(attachment_id: str, body: _Detach, request: Request):
        if not _local_transport(request) or not same_origin_request(request) or request.query_params:
            return _error(403, 'PERMISSION_DENIED', 'Local operator access is required.')
        state = request.app.state
        reference = await _worker(state.operator_auth.authority_reference, token=request.cookies.get(COOKIE), create=False)
        if reference is None:
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to detach this presentation.')
        services = _services(state, body.presentation)
        if services is None:
            return _error(409, 'CONFLICT', 'This local presentation is currently unavailable.')
        try:
            await _worker(services.broker.detach, scope=body.input_scope(), channel_id=body.channel_id,
                          author=InputAuthor(reference, 'native_terminal'), attachment_id=attachment_id)
        except OktoNexusError as error:
            return _runtime_error(error)
        return JSONResponse({'version': 1, 'state': 'DETACHED'}, headers=_HEADERS)

    return router
