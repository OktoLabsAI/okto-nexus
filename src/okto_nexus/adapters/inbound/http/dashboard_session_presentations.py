"""Authenticated operator transport for scoped native presenters."""

import asyncio
import re
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
from nexus_connector_core.native.pi_renderer import PiEditorUpdate
from nexus_connector_core.protocol import canonical_json, strict_json
from pydantic import Field, TypeAdapter

from ....adapters.outbound.execution.core_inventory import protocol_info
from ....application.codex_presenter_channel import CodexPresenterHistoryChannel
from ....application.codex_viewer_protocol import CodexViewerContext
from ....application.execution_native_session_mapping import ManagedNativeSession
from ....application.session_attachment_broker import SessionAttachmentBroker
from ....application.session_interaction_authority import enqueue_human_input
from ....application.session_interaction_controls import read_human_interrupt_receipt, request_exact_human_interrupt
from ....application.session_interaction_promotion import steer_human_input
from ....application.session_interaction_receipts import read_session_input_receipt
from ....domain.presentation_protocol import (
    BROWSER_PRESENTATION_PROTOCOL,
    CLAUDE_PRESENTATION_SUBPROTOCOL,
    LOCAL_CODEX_AUDIENCE,
    LOCAL_PI_AUDIENCE,
    LOCAL_CLAUDE_AUDIENCE,
    MAX_PI_PRESENTATION_BYTES,
    MAX_PRESENTATION_REQUEST_BYTES,
    MAX_PRESENTATION_RESPONSE_BYTES,
    PRESENTATION_SUBPROTOCOL,
    PI_PRESENTATION_SUBPROTOCOL,
    REMOTE_CLAUDE_AUDIENCE,
    REMOTE_CLAUDE_SUBPROTOCOL,
    REMOTE_PI_AUDIENCE,
    REMOTE_PI_SUBPROTOCOL,
    REMOTE_CODEX_AUDIENCE,
    REMOTE_CODEX_SUBPROTOCOL,
)
from ....domain.session_interaction import InputAuthor, InputDeliveryState, InputScope
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
    ClaudeOperationTarget,
    Identifier,
    InterruptTargetView,
    NativeTurnTarget,
    ObservedRunTarget,
    PrepareAttachment,
    Revision,
    ScopedSession,
    SteerTargetView,
    TextInput,
    _Document,
)

_PRESENTERS = {
    'codex': ('local_codex_presentations', LOCAL_CODEX_AUDIENCE, PRESENTATION_SUBPROTOCOL),
    'pi': ('local_pi_presentations', LOCAL_PI_AUDIENCE, PI_PRESENTATION_SUBPROTOCOL),
    'claude': ('local_claude_presentations', LOCAL_CLAUDE_AUDIENCE, CLAUDE_PRESENTATION_SUBPROTOCOL),
    'codex_remote': ('remote_codex_presentations', REMOTE_CODEX_AUDIENCE, REMOTE_CODEX_SUBPROTOCOL),
    'pi_remote': ('remote_pi_presentations', REMOTE_PI_AUDIENCE, REMOTE_PI_SUBPROTOCOL),
    'claude_remote': ('remote_claude_presentations', REMOTE_CLAUDE_AUDIENCE, REMOTE_CLAUDE_SUBPROTOCOL),
}

_PI_BROWSER_COMMANDS = {'/help', '/status', '/interrupt'}
_PI_COMMAND_PREFIX = re.compile(r'/[a-z]{0,32}')
_REMOTE = frozenset({'codex_remote', 'pi_remote', 'claude_remote'})
_PI = frozenset({'pi', 'pi_remote'})
_CLAUDE = frozenset({'claude', 'claude_remote'})
_TERMINAL = _PI | _CLAUDE
_RENEW_SECONDS = 15
_SEND_SECONDS = 5
_CLOSE_SECONDS = 2


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
    open_editor: Callable[..., AbstractAsyncContextManager] | None = None
    writer_locks: WeakValueDictionary[InputScope, asyncio.Lock] = field(default_factory=WeakValueDictionary,
                                                                        repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class LocalClaudePresentations:
    broker: SessionAttachmentBroker
    prove_owner: Callable[[InputScope], Awaitable[tuple[ManagedNativeSession, NativeSessionOwnerProof]]]
    open_reader: Callable[..., AbstractAsyncContextManager[AsyncIterator[bytes]]]
    execution_access: object | None = None
    next_turn_revision: Callable[[object, InputScope], str | None] | None = None


@dataclass(frozen=True, slots=True)
class RemoteCodexPresentations:
    broker: SessionAttachmentBroker
    source: object
    execution_access: object
    live_updates: bool = True
    next_turn_revision: Callable[[object, InputScope], str | None] | None = None

    async def prove_owner(self, scope, *, author):
        return await self.source.prove(scope, author=author)

    async def read_context(self, scope, *, author):
        _, context = await self.source.read(scope, author)
        return context


class _Hello(ScopedSession):
    kind: Literal['hello']
    version: Literal[1]


class _PiHello(_Hello):
    columns: Annotated[int, Field(strict=True, ge=24, le=300)]
    rows: Annotated[int, Field(strict=True, ge=8, le=120)]
    editor: bool = False


class _BrowserPiHello(_PiHello):
    ticket: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{43}$', min_length=43, max_length=43)]


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


class _TerminalEnqueueRequest(_Document):
    kind: Literal['enqueue']
    request_id: Revision
    client_intent_id: Identifier
    capability_revision: Identifier
    content: TextInput


class _PiKeyRequest(_Document):
    kind: Literal['key']
    request_id: Revision
    client_intent_id: Identifier
    capability_revision: Identifier
    key: Literal['insert', 'enter', 'newline', 'backspace', 'delete', 'left', 'right', 'up', 'down', 'home', 'end',
                 'command_preview']
    text: Annotated[str, Field(max_length=4096)] | None = None


class _TerminalControlReviewRequest(_Document):
    kind: Literal['steer_review', 'interrupt_review']
    request_id: Revision
    client_intent_id: Identifier
    capability_revision: Identifier


class _ClaudeSteerReviewRequest(_TerminalControlReviewRequest):
    kind: Literal['steer_review']
    content: TextInput


class _TerminalControlDecisionRequest(_Document):
    kind: Literal['steer_confirm', 'steer_cancel', 'interrupt_confirm', 'interrupt_cancel']
    request_id: Revision
    review_id: Identifier


class _PiSteerStatusRequest(_Document):
    kind: Literal['steer_status']
    request_id: Revision
    input_id: Identifier


class _PiInterruptStatusRequest(_Document):
    kind: Literal['interrupt_status']
    request_id: Revision
    client_intent_id: Identifier


class _EnqueueRequest(_TerminalEnqueueRequest):
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


@dataclass(frozen=True, slots=True)
class _ReviewedTerminalControl:
    id: str
    expires: float
    request: _TerminalControlReviewRequest
    target: SteerTargetView | InterruptTargetView
    text: str | None = field(default=None, repr=False)


_REQUEST = TypeAdapter(Annotated[_HistoryRequest | _ContextRequest | _UpdatesRequest | _EnqueueRequest
                                 | _InputDeliveryRequest | _SteerReviewRequest | _InterruptReviewRequest
                                 | _TurnConfirmRequest | _InterruptReceiptRequest,
                                 Field(discriminator='kind')])


class _Review(ScopedSession):
    access: Literal['read', 'write'] = 'read'
    presentation: Literal['codex', 'pi', 'claude', 'codex_remote', 'pi_remote', 'claude_remote'] = 'codex'


class _Detach(ScopedSession):
    channel_id: Identifier
    presentation: Literal['codex', 'pi', 'claude', 'codex_remote', 'pi_remote', 'claude_remote'] = 'codex'


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


def _transport(request, *, remote):
    return _local_transport(request) or remote and request.url.scheme in ('https', 'wss')


def _presentation_post(request, presentation):
    remote = presentation in _REMOTE
    return (_transport(request, remote=remote) and same_origin_request(request) and
            (not remote or (request.headers.getlist('origin') == [f'{request.url.scheme}://{request.url.netloc}']
                            and request.headers.get('x-nexus-operator-session-required') == '1')))


def _upgrade_allowed(ws: WebSocket, protocol=PRESENTATION_SUBPROTOCOL) -> bool:
    remote = any(_PRESENTERS[name][2] == protocol for name in _REMOTE)
    if (not _transport(ws, remote=remote) or ws.query_params or ws.headers.get('sec-fetch-site') == 'cross-site'
            or len(ws.headers.getlist('origin')) > 1
            or remote and not ws.headers.get('origin')
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
    with anyio.fail_after(_SEND_SECONDS):
        await ws.send_text(raw.decode())


def _services(state, presentation='codex'):
    if presentation in _REMOTE and not (state.deps.config.runtime_session_interaction_enabled
                                        and state.deps.config.feature_harness_integrations):
        return None
    return getattr(state, _PRESENTERS[presentation][0], None)


def _author_callback(callback, author, presentation):
    return partial(callback, author=author) if presentation in _REMOTE else callback


def _matching_presenter(mapping, presentation) -> bool:
    if presentation in _CLAUDE:
        return mapping.adapter_id == 'claude_stream'
    return mapping.adapter_id == 'pi_rpc' if presentation in _PI else mapping.codex_thread_id is not None


def _verify_writer(state, services, active, uow, human, *, presentation):
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
    if target is None or not isinstance(target.target, NativeTurnTarget) or target.target.turn_id != request.turn_id:
        return None
    return _ReviewedTurn(secrets.token_urlsafe(24), time.monotonic() + 45, request, target)


async def _confirm_turn(state, services, active, history, review, request, *, presentation):
    if (review is None or request.review_id != review.id or time.monotonic() >= review.expires
            or (request.kind == 'steer_confirm') != isinstance(review.request, _SteerReviewRequest)):
        return {'status': 'refused'}
    await history.verify_input_thread(review.request.thread_id)

    def cut(uow, human):
        if time.monotonic() >= review.expires:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The turn review expired.', {})
        _verify_writer(state, services, active, uow, human, presentation=presentation)

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


async def _enqueue(state, services, active, history, request, *, presentation):
    if active['attachment'].access != 'write' or services.next_turn_revision is None:
        raise ValueError('This presentation cannot enqueue input')
    await history.verify_input_thread(request.thread_id)
    return await _record_presenter_input(state, services, active, request, presentation=presentation)


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


def _review_terminal_control(state, services, active, request, text=None, *, claude=False):
    steering = request.kind == 'steer_review'
    if steering and (not text or not text.strip() or text.lstrip().startswith(('/', '!'))):
        return None
    if steering and claude and any(char != '\n' and (char < ' ' or '\x7f' <= char <= '\x9f') for char in text):
        return None
    with services.broker.factory.unit_of_work(write=False) as uow:
        if services.next_turn_revision(uow, active['scope']) != request.capability_revision:
            return None
        if steering:
            target = review_exact_steer(uow, active['scope'], services.next_turn_revision,
                remote_control_host=state.deps.runtime_availability.current_host)
            effect = 'interrupt_then_send' if claude else 'next_boundary'
            if target is not None and target.effect != effect:
                return None
        else:
            target = review_exact_interrupt(uow, active['scope'], _interrupt_target_for(state))
        target_type = ClaudeOperationTarget if claude else ObservedRunTarget
        if target is None or not isinstance(target.target, target_type):
            return None
        return _ReviewedTerminalControl(secrets.token_urlsafe(24), time.monotonic() + 45, request, target, text)


def _terminal_review_reply(review):
    if review is None:
        return {'status': 'unavailable'}
    response = {'status': 'reviewed', 'review_id': review.id}
    if isinstance(review.target.target, ClaudeOperationTarget):
        response['operation_id'] = review.target.target.operation_id
    return response


async def _decide_terminal_control(state, services, active, request, review, *, presentation):
    action, decision = request.kind.split('_')
    if review is None or request.review_id != review.id or review.request.kind != f'{action}_review':
        return {'status': 'refused'}
    if decision == 'cancel':
        return {'status': 'cancelled'}

    def cut(uow, human):
        if time.monotonic() >= review.expires:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The terminal control review expired.', {})
        _verify_writer(state, services, active, uow, human, presentation=presentation)

    target = review.target.target
    selection = ({'native_turn_id': target.operation_id, 'claude_operation': True}
                 if isinstance(target, ClaudeOperationTarget) else {'native_turn_id': target.run_ref, 'observed_run': True})
    common = dict(factory=services.broker.factory, access=services.execution_access,
        authority_fence=services.broker.authority_fence, scope=active['scope'], author=active['author'],
        client_intent_id=review.request.client_intent_id, **selection,
        capability_revision=review.target.capability_revision, expected_queue_revision=review.target.queue_revision,
        fresh_publications=state.inventory_fresh_publications, remote_ready=protocol_info()['remote_execution_ready'],
        verify_presenter=cut)
    try:
        if action == 'interrupt':
            target_for = _interrupt_target_for(state)
            if target_for is None:
                return {'status': 'refused'}
            await _worker(request_exact_human_interrupt, current_interrupt_target=target_for, **common)
            return {'status': 'recorded'}
        revisions = getattr(state, 'session_input_dispatch_options', {}).get('session_steer_revisions')
        if revisions is None or not isinstance(review.target, SteerTargetView):
            return {'status': 'refused'}
        receipt = await _worker(steer_human_input, current_steer_revisions=revisions, text=review.text,
                                confirmed_effect_revision=review.target.effect_revision, **common)
    except OktoNexusError as error:
        if error.code in (ErrorCode.CONFLICT, ErrorCode.PERMISSION_DENIED, ErrorCode.VALIDATION_ERROR, ErrorCode.NOT_FOUND):
            return {'status': 'refused'}
        raise
    return {'status': 'recorded', 'input_id': receipt.input_id}


def _read_pi_draft_status(services, active, input_id):
    broker = services.broker
    with broker.authority_fence() as human:
        receipt = read_session_input_receipt(broker.factory, access=services.execution_access, resolve_human=human,
            scope=active['scope'], author=active['author'], input_id=input_id)
    if not receipt.reorientation or receipt.operation_id is None:
        raise ValueError('The receipt is not a recorded reorientation')
    if receipt.steer_boundary is not None:
        return receipt.steer_boundary
    if receipt.status == InputDeliveryState.REFUSED_BEFORE_SEND and not receipt.possible_effect:
        return 'refused'
    if receipt.status == InputDeliveryState.DELIVERY_UNKNOWN:
        return 'unconfirmed'
    return 'submitted' if receipt.steer_submitted else 'pending'


def _read_pi_interrupt_status(state, services, active, client_intent_id):
    broker = services.broker
    with broker.authority_fence() as human:
        receipt = read_human_interrupt_receipt(broker.factory, access=services.execution_access, resolve_human=human,
            scope=active['scope'], author=active['author'], client_intent_id=client_intent_id,
            current_interrupt_target=_interrupt_target_for(state))
    return {'target_status': receipt['interrupt']['target_status'],
            'queue_paused': receipt['interrupt']['queue_paused'],
            'refused': bool(receipt.get('error')) and not receipt['possible_effect'],
            'outcome_unknown': receipt.get('executor_stage') == 'OUTCOME_UNKNOWN'}


async def _reply_terminal(ws, request, value):
    await _send(ws, {'kind': request.kind, 'request_id': request.request_id, request.kind: value})


async def _present_pi(ws, services, active, hello, *, presentation, browser=False):
    access = active['attachment'].access
    state = ws.app.state
    remote = presentation == 'pi_remote'

    async def verify(*, renew=False):
        if _services(state, presentation) is not services:
            raise ValueError('Presentation owner changed')
        await _worker(services.broker.refresh if renew else services.broker.require_active, **active)
        if _services(state, presentation) is not services:
            raise ValueError('Presentation owner changed')

    async with AsyncExitStack() as stack:
        with anyio.fail_after(10):
            if access == 'write':
                # A replaced writer releases its renderer before the new writer opens one.
                lock = services.writer_locks.setdefault(active['scope'], asyncio.Lock())
                await stack.enter_async_context(lock)
            await verify()
            viewport = {'columns': hello.columns, 'rows': hello.rows}
            if hello.editor:
                if access != 'write' or services.open_editor is None or services.next_turn_revision is None:
                    raise ValueError('This presentation cannot open a draft editor')
                open_editor = _author_callback(services.open_editor, active['author'], presentation)
                edit, read_output = await stack.enter_async_context(open_editor(active['scope'], **viewport))
            else:
                open_renderer = _author_callback(services.open_renderer, active['author'], presentation)
                frames = await stack.enter_async_context(open_renderer(active['scope'], **viewport))

                async def read_output():
                    return await anext(frames, None)

            await verify()
            await _send(ws, {'kind': 'attached', 'attachment_id': active['attachment'].attachment_id, 'access': access})

        inbound = asyncio.create_task(ws.receive())
        output = asyncio.create_task(read_output())
        pending = review = admitted_steer = admitted_interrupt = None
        checking_submission = False
        browser_command = None
        renewal = anyio.current_time() + _RENEW_SECONDS
        try:
            while True:
                done, _ = await asyncio.wait((inbound, output), timeout=1, return_when=asyncio.FIRST_COMPLETED)
                received = inbound in done
                raw = None
                if received:
                    message = inbound.result()
                    if message['type'] == 'websocket.disconnect':
                        return
                    raw = _decode(message)
                    inbound = asyncio.create_task(ws.receive())
                keepalive = remote and raw == {'kind': 'keepalive'}
                renewal_due = anyio.current_time() >= renewal
                renew = renewal_due and (not remote or keepalive)
                await verify(renew=renew)
                if renew:
                    renewal = anyio.current_time() + _RENEW_SECONDS
                if received and not keepalive:
                    if access != 'write' or services.next_turn_revision is None:
                        raise ValueError('This presentation cannot enqueue input')
                    if pending is not None:
                        raise ValueError('The draft editor already has a pending request')
                    kind = raw.get('kind') if isinstance(raw, dict) else None
                    if hello.editor and kind == 'steer_status':
                        request = _PiSteerStatusRequest.model_validate(raw)
                        if request.input_id != admitted_steer:
                            raise ValueError('The draft has no matching reorientation')
                        status = await _worker(_read_pi_draft_status, services=services, active=active, input_id=admitted_steer)
                        if status == 'applied':
                            pending = request
                            await edit('clear', text=None)
                        else:
                            if status in ('discarded', 'refused'):
                                admitted_steer = None
                            await _reply_terminal(ws, request, {'status': status})
                    elif hello.editor and kind == 'interrupt_status':
                        request = _PiInterruptStatusRequest.model_validate(raw)
                        if request.client_intent_id != admitted_interrupt:
                            raise ValueError('The editor has no matching interruption')
                        result = await _worker(_read_pi_interrupt_status, state=state, services=services, active=active,
                                               client_intent_id=admitted_interrupt)
                        if result['target_status'] in ('interrupted', 'finished') or result['refused']:
                            admitted_interrupt = None
                        await _reply_terminal(ws, request, result)
                    elif hello.editor and kind in ('steer_review', 'interrupt_review'):
                        review = None
                        request = _TerminalControlReviewRequest.model_validate(raw)
                        if kind == 'steer_review' and admitted_steer is None:
                            pending = request
                            await edit('snapshot', text=None)
                        else:
                            if kind == 'interrupt_review' and admitted_interrupt is None:
                                review = await _worker(_review_terminal_control, state=state, services=services,
                                                       active=active, request=request)
                            await _reply_terminal(ws, request, _terminal_review_reply(review))
                    elif hello.editor and kind in ('steer_confirm', 'steer_cancel', 'interrupt_confirm', 'interrupt_cancel'):
                        request = _TerminalControlDecisionRequest.model_validate(raw)
                        selected, review = review, None
                        reply = await _decide_terminal_control(state, services, active, request, selected, presentation=presentation)
                        if reply['status'] == 'recorded':
                            if kind == 'interrupt_confirm':
                                admitted_interrupt = selected.request.client_intent_id
                            else:
                                admitted_steer = reply['input_id']
                        await _reply_terminal(ws, request, reply)
                    elif hello.editor and admitted_steer is not None:
                        raise ValueError('A reorientation holds the draft until its receipt is known')
                    elif hello.editor and kind == 'key':
                        review = None
                        pending = _PiKeyRequest.model_validate(raw)
                        if pending.key == 'command_preview' and not browser:
                            raise ValueError('Command previews are available only in the browser')
                        checking_submission = browser and pending.key == 'enter'
                        if checking_submission or pending.key == 'command_preview':
                            if pending.text is not None:
                                raise ValueError('The draft snapshot does not take input text')
                            await edit('snapshot', text=None)
                        else:
                            await edit(pending.key, text=pending.text)
                    else:
                        review = None
                        request = _TerminalEnqueueRequest.model_validate(raw)
                        reply = await _record_presenter_input(state, services, active, request, presentation=presentation)
                        if _services(state, presentation) is not services:
                            break
                        await _send(ws, {'request_id': request.request_id, **reply})
                    if remote and renewal_due:
                        await verify(renew=True)
                        renewal = anyio.current_time() + _RENEW_SECONDS
                if output not in done:
                    continue
                data = output.result()
                if data is None:
                    break
                if hello.editor and isinstance(data, PiEditorUpdate):
                    if pending is None:
                        raise ValueError('The draft editor response is unsolicited')
                    if isinstance(pending, _TerminalControlReviewRequest):
                        review = await _worker(_review_terminal_control, state=state, services=services, active=active,
                                               request=pending, text=data.draft)
                        reply = _terminal_review_reply(review)
                    elif isinstance(pending, _PiSteerStatusRequest):
                        if data.draft is not None or data.limit_reached:
                            raise ValueError('The renderer did not clear the applied draft')
                        admitted_steer = None
                        reply = {'status': 'applied'}
                    elif pending.key == 'command_preview':
                        draft = (data.draft or '').lower()
                        reply = {'limit_reached': False, 'queued': None,
                                 'command_prefix': draft if _PI_COMMAND_PREFIX.fullmatch(draft) else None}
                    elif checking_submission:
                        checking_submission = False
                        draft = (data.draft or '').strip()
                        if draft.startswith(('/', '!')) and draft.lower() not in _PI_BROWSER_COMMANDS:
                            reply = {'limit_reached': False, 'queued': None,
                                     'command': {'name': 'unavailable', 'draft_kept': True}}
                        else:
                            browser_command = draft.lower() if draft.startswith('/') else None
                            await edit('clear' if browser_command else 'enter', text=None)
                            output = asyncio.create_task(read_output())
                            continue
                    else:
                        queued = None
                        command = None
                        if browser_command is not None:
                            if data.draft is not None or data.limit_reached:
                                raise ValueError('The renderer did not clear the command')
                            command = {'name': browser_command[1:]}
                            browser_command = None
                            if command['name'] == 'interrupt':
                                request = _TerminalControlReviewRequest(kind='interrupt_review', request_id=pending.request_id,
                                    client_intent_id=pending.client_intent_id, capability_revision=pending.capability_revision)
                                review = await _worker(_review_terminal_control, state=state, services=services, active=active,
                                                       request=request)
                                command.update(_terminal_review_reply(review))
                        elif data.draft is not None:
                            if pending.key != 'enter' or data.limit_reached:
                                raise ValueError('The draft editor response does not match the key')
                            if browser and data.draft.lstrip().startswith(('/', '!')):
                                raise ValueError('The renderer submission changed after review')
                            request = _TerminalEnqueueRequest(kind='enqueue', request_id=pending.request_id,
                                client_intent_id=pending.client_intent_id, capability_revision=pending.capability_revision,
                                content=TextInput(type='text', text=data.draft))
                            queued = await _record_presenter_input(state, services, active, request, presentation=presentation)
                        reply = {'limit_reached': data.limit_reached, 'queued': queued}
                        if command is not None:
                            reply['command'] = command
                    if _services(state, presentation) is not services:
                        break
                    await _reply_terminal(ws, pending, reply)
                    pending = None
                elif type(data) is not bytes or not 1 <= len(data) <= MAX_PI_PRESENTATION_BYTES:
                    raise ValueError('Invalid renderer frame')
                else:
                    with anyio.fail_after(_SEND_SECONDS):
                        await ws.send_bytes(data)
                output = asyncio.create_task(read_output())
        finally:
            inbound.cancel()
            output.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.gather(inbound, output, return_exceptions=True)
    return 4409


async def _present_claude(ws, services, active, *, presentation):
    access = active['attachment'].access
    if access == 'write' and services.next_turn_revision is None:
        raise ValueError('Claude terminal input is unavailable')
    state = ws.app.state
    remote = presentation == 'claude_remote'

    async def verify(renew=False):
        if _services(ws.app.state, presentation) is not services:
            raise ValueError('Presentation owner changed')
        await _worker(services.broker.refresh if renew else services.broker.require_active, **active)
        if _services(ws.app.state, presentation) is not services:
            raise ValueError('Presentation owner changed')

    async with AsyncExitStack() as stack:
        with anyio.fail_after(10):
            await verify()
            open_reader = _author_callback(services.open_reader, active['author'], presentation)
            frames = await stack.enter_async_context(open_reader(active['scope']))
            await verify()
            await _send(ws, {'kind': 'attached', 'attachment_id': active['attachment'].attachment_id, 'access': access})
        inbound = asyncio.create_task(ws.receive())
        output = asyncio.create_task(anext(frames, None))
        renew_at = anyio.current_time() + _RENEW_SECONDS
        review = None
        try:
            while True:
                done, _ = await asyncio.wait((inbound, output),
                    timeout=1 if remote else max(0, renew_at - anyio.current_time()),
                    return_when=asyncio.FIRST_COMPLETED)
                keepalive = False
                if inbound in done:
                    message = inbound.result()
                    if message['type'] == 'websocket.disconnect':
                        return
                    raw = _decode(message)
                    if remote and raw == {'kind': 'keepalive'}:
                        keepalive = True
                    elif access == 'write':
                        kind = raw.get('kind') if isinstance(raw, dict) else None
                        if kind in ('steer_review', 'interrupt_review'):
                            await verify()
                            if kind == 'steer_review':
                                request = _ClaudeSteerReviewRequest.model_validate(raw)
                                text = request.content.text
                            else:
                                request = _TerminalControlReviewRequest.model_validate(raw)
                                text = None
                            review = await _worker(_review_terminal_control, state=state, services=services,
                                                   active=active, request=request, text=text, claude=True)
                            await _reply_terminal(ws, request, _terminal_review_reply(review))
                        elif kind in ('steer_confirm', 'steer_cancel', 'interrupt_confirm', 'interrupt_cancel'):
                            request = _TerminalControlDecisionRequest.model_validate(raw)
                            selected, review = review, None
                            result = await _decide_terminal_control(state, services, active, request, selected,
                                                                     presentation=presentation)
                            await _reply_terminal(ws, request, result)
                        else:
                            review = None
                            request = _TerminalEnqueueRequest.model_validate(raw)
                            result = await _record_presenter_input(state, services, active, request,
                                                                   presentation=presentation)
                            await _send(ws, {'request_id': request.request_id, **result})
                    else:
                        raise ValueError('Claude terminal attachment does not accept input')
                    inbound = asyncio.create_task(ws.receive())
                if anyio.current_time() >= renew_at:
                    renew = not remote or keepalive
                    await verify(renew=renew)
                    if renew:
                        renew_at = anyio.current_time() + _RENEW_SECONDS
                if output in done:
                    frame = output.result()
                    if frame is None:
                        break
                    if type(frame) is not bytes or not 1 <= len(frame) <= MAX_PI_PRESENTATION_BYTES:
                        raise ValueError('Invalid terminal frame')
                    await verify()
                    with anyio.fail_after(_SEND_SECONDS):
                        await ws.send_bytes(frame)
                    output = asyncio.create_task(anext(frames, None))
        finally:
            inbound.cancel()
            output.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.gather(inbound, output, return_exceptions=True)
    return 1000


async def _present(ws, services, author, attachment_id, ticket, presentation):
    broker = services.broker
    pi = presentation in _PI
    remote = presentation == 'codex_remote'
    browser = ticket is None
    _, audience, protocol = _PRESENTERS[presentation]
    channel_id = 'viewer_' + secrets.token_hex(16)
    scope = None
    close_code = None
    await ws.accept(subprotocol=protocol)
    try:
        with anyio.fail_after(10):
            document = await _receive(ws)
            if ticket is None:
                hello = _BrowserPiHello.model_validate(document)
                ticket = hello.ticket
            else:
                hello = (_PiHello if pi else _Hello).model_validate(document)
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
            if remote:
                await services.read_context(scope, author=author)
                await _worker(broker.require_active, **active)
                if _services(ws.app.state, presentation) is not services:
                    raise ValueError('Presentation owner changed')
            if presentation not in _TERMINAL:
                await _send(ws, {'kind': 'attached', 'attachment_id': attachment_id, 'access': attachment.access})
        if presentation in _CLAUDE:
            close_code = await _present_claude(ws, services, active, presentation=presentation)
            return
        if pi:
            close_code = await _present_pi(ws, services, active, hello, presentation=presentation, browser=browser)
            return
        prove_owner = _author_callback(services.prove_owner, author, presentation)
        read_context = _author_callback(services.read_context, author, presentation)
        history = CodexPresenterHistoryChannel(broker=broker, prove_owner=prove_owner,
                                              access=services.execution_access, **active)
        next_check = next_renewal = anyio.current_time() + _RENEW_SECONDS
        reviewed = None
        while _services(ws.app.state, presentation) is services:
            with anyio.move_on_after(max(0, next_check - anyio.current_time())) as deadline:
                raw = await _receive(ws)
            if deadline.cancel_called:
                # A live transport alone doesn't prove that the remote terminal
                # is still receiving and processing the application stream.
                await _worker(broker.require_active if remote else broker.refresh, **active)
                next_check = anyio.current_time() + _RENEW_SECONDS
                continue
            request = _REQUEST.validate_python(raw)
            if (remote and attachment.access == 'read'
                    and not isinstance(request, (_ContextRequest, _HistoryRequest, _UpdatesRequest))):
                raise ValueError('Remote Codex presentation is read-only')
            if isinstance(request, _ContextRequest):
                if read_context is None:
                    raise ValueError('Presentation context is unavailable')
                context = await history.viewer_context(read_context,
                    can_follow=services.live_updates and request.follow is True)
                reply = {'kind': 'context', 'context': context.model_dump(mode='json')}
            elif isinstance(request, _HistoryRequest):
                page = await history.page(method=request.method, params=request.params)
                reply = {'kind': 'page', 'page': page}
            elif isinstance(request, _EnqueueRequest):
                reply = await _enqueue(ws.app.state, services, active, history, request, presentation=presentation)
            elif isinstance(request, _InputDeliveryRequest):
                reply = {'kind': 'input_delivery', 'input_delivery': await history.input_delivery(request.input_id)}
            elif isinstance(request, _TurnReviewRequest):
                reviewed = await _review_turn(ws.app.state, services, active, history, request)
                control = {'review_id': reviewed.id, 'turn_id': request.turn_id} if reviewed else {}
                reply = {'kind': request.kind, request.kind: control}
            elif isinstance(request, _TurnConfirmRequest):
                review, reviewed = reviewed, None
                control = await _confirm_turn(ws.app.state, services, active, history, review, request,
                                              presentation=presentation)
                reply = {'kind': request.kind, request.kind: control}
            elif isinstance(request, _InterruptReceiptRequest):
                receipt = await history.interrupt_receipt(thread_id=request.thread_id, intent=request.client_intent_id,
                    current_interrupt_target=_interrupt_target_for(ws.app.state))
                reply = {'kind': 'interrupt_receipt', 'interrupt_receipt': receipt}
            else:
                if not services.live_updates:
                    raise ValueError('Presentation updates are unavailable')
                reply = {'kind': 'updates', 'updates': await history.updates()}
            if _services(ws.app.state, presentation) is not services:
                break
            if remote and anyio.current_time() >= next_renewal:
                await _worker(broker.refresh, **active)
                next_renewal = anyio.current_time() + _RENEW_SECONDS
            await _send(ws, {'request_id': request.request_id, **reply})
        close_code = 4409
    except WebSocketDisconnect:
        return
    except (CoreError, OktoNexusError, ValueError, RecursionError, TimeoutError):
        close_code = 4409
    finally:
        if scope is not None:
            with anyio.CancelScope(shield=True):
                await _worker(broker.disconnect, scope=scope, attachment_id=attachment_id, channel_id=channel_id)
        # The same backpressure that blocked output can also block the close frame.
        if close_code is not None:
            try:
                with anyio.move_on_after(_CLOSE_SECONDS):
                    await ws.close(code=close_code)
            except WebSocketDisconnect:
                pass


def build_router():
    router = APIRouter()

    @router.post('/sessions/{session_id}/attachments:review')
    async def review(session_id: str, body: _Review, request: Request):
        if not _presentation_post(request, body.presentation):
            return _error(403, 'PERMISSION_DENIED', 'This presentation requires a trusted operator connection.')
        if session_id != body.scope.session_id or request.query_params:
            return _error(422, 'VALIDATION_ERROR', 'An exact presentation scope is required.')
        state = request.app.state
        token = request.cookies.get(COOKIE)
        if await _worker(state.operator_auth.resolve, token=token) is None:
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to review this presentation.')
        terminal = body.presentation in _TERMINAL
        services = _services(state, body.presentation)
        writing = body.access == 'write'
        if (services is None or writing and services.next_turn_revision is None
                or not terminal and services.read_context is None):
            return _error(409, 'CONFLICT', 'This presentation is currently unavailable.')
        scope = body.input_scope()
        try:
            reference = await _worker(state.operator_auth.authority_reference, token=token)
            if reference is None:
                return _error(401, 'AUTH_FAILED', 'The operator login has expired.')
            author = InputAuthor(reference, 'native_terminal')
            authority = {'scope': scope, 'author': author, 'audience': _PRESENTERS[body.presentation][1]}
            mapping, _ = await _author_callback(services.prove_owner, author, body.presentation)(scope)
            if not _matching_presenter(mapping, body.presentation) or _services(state, body.presentation) is not services:
                raise CoreError('SESSION_CONFLICT', 'native_presentation')
            review_capability = services.broker.review_writer if writing else services.broker.review_reader
            reviewed = await _worker(review_capability, **authority)
            if not terminal:
                context = await _author_callback(services.read_context, author, body.presentation)(scope)
                if context is None or context.thread_id != mapping.codex_thread_id:
                    raise CoreError('SESSION_CONFLICT', 'native_presentation')
            if (reviewed != await _worker(review_capability, **authority)
                    or _services(state, body.presentation) is not services):
                raise CoreError('SESSION_CONFLICT', 'native_presentation')
            strategy = body.presentation if body.presentation in _REMOTE else f'{body.presentation}_local'
            details = {'attach_strategy': f'{strategy}_read', 'capability_revision': reviewed}
            if writing:
                def input_revision():
                    with services.broker.factory.unit_of_work(write=False) as uow:
                        return services.next_turn_revision(uow, scope)

                revision = await _worker(input_revision)
                if revision is None or _services(state, body.presentation) is not services:
                    raise CoreError('SESSION_CONFLICT', 'native_presentation')
                details = {'attach_strategy': f'{strategy}_write', 'capability_revision': reviewed.capability_revision,
                    'writer_epoch': reviewed.epoch, 'writer_occupied': reviewed.occupied,
                    'input_capability_revision': revision}
        except OktoNexusError as error:
            return _runtime_error(error)
        except CoreError:
            return _error(409, 'CONFLICT', 'This presentation is currently unavailable.')
        return JSONResponse({'version': 1, **details, **body.model_dump(exclude={'access', 'presentation'})}, headers=_HEADERS)

    @router.post('/sessions/{session_id}/attachments:prepare')
    async def prepare(session_id: str, body: PrepareAttachment, request: Request):
        if not _presentation_post(request, body.presentation):
            return _error(403, 'PERMISSION_DENIED', 'This presentation requires a trusted operator connection.')
        if session_id != body.scope.session_id or request.query_params:
            return _error(422, 'VALIDATION_ERROR', 'An exact presentation scope is required.')
        state = request.app.state
        token = request.cookies.get(COOKIE)
        if await _worker(state.operator_auth.resolve, token=token) is None:
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to prepare this presentation.')
        terminal = body.presentation in _TERMINAL
        services = _services(state, body.presentation)
        if (services is None or body.intent != 'attach_live'
                or body.access == 'write' and services.next_turn_revision is None):
            return _error(409, 'CONFLICT', 'This presentation is currently unavailable.')
        scope = body.input_scope()
        try:
            reference = await _worker(state.operator_auth.authority_reference, token=token)
            if reference is None:
                return _error(401, 'AUTH_FAILED', 'The operator login has expired.')
            author = InputAuthor(reference, 'native_terminal')
            mapping, _ = await _author_callback(services.prove_owner, author, body.presentation)(scope)
            if not _matching_presenter(mapping, body.presentation) or _services(state, body.presentation) is not services:
                raise CoreError('SESSION_CONFLICT', 'native_presentation')
            offer = await _worker(services.broker.prepare, scope=scope, author=author,
                audience=_PRESENTERS[body.presentation][1],
                capability_revision=body.capability_revision, client_intent_id=body.client_intent_id,
                access=body.access, expected_writer_epoch=body.expected_writer_epoch, takeover=body.takeover)
        except OktoNexusError as error:
            return _runtime_error(error)
        except CoreError:
            return _error(409, 'CONFLICT', 'This presentation is currently unavailable.')
        features = {'pi_keepalive': True} if body.presentation == 'pi_remote' else {}
        if body.presentation == 'claude_remote':
            features = {'claude_keepalive': True}
        return JSONResponse({'version': 1, 'attachment_id': offer.attachment_id, 'state': offer.state,
                             'ticket': offer.ticket, 'live_updates': True if terminal else services.live_updates,
                             **features},
                            status_code=201 if offer.ticket else 200, headers=_HEADERS)

    @router.websocket('/attachments/{attachment_id}/stream')
    async def stream(ws: WebSocket, attachment_id: str):
        offered = set(ws.scope.get('subprotocols', ()))
        recognized = [name for name, (_, _, protocol) in _PRESENTERS.items() if protocol in offered]
        if len(recognized) != 1:
            await ws.close(code=4403)
            return
        presentation = recognized[0]
        protocol = _PRESENTERS[presentation][2]
        services, ticket = _services(ws.app.state, presentation), _ticket(ws)
        browser = BROWSER_PRESENTATION_PROTOCOL in offered
        if browser:
            origin_scheme = 'https' if ws.url.scheme == 'wss' else 'http'
            if (presentation not in _PI or offered != {protocol, BROWSER_PRESENTATION_PROTOCOL}
                    or 'authorization' in ws.headers
                    or ws.headers.getlist('origin') != [f'{origin_scheme}://{ws.url.netloc}']):
                await ws.close(code=4403)
                return
        if services is None or (not browser and ticket is None) or not _upgrade_allowed(ws, protocol):
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
        if not _presentation_post(request, body.presentation) or request.query_params:
            return _error(403, 'PERMISSION_DENIED', 'This presentation requires a trusted operator connection.')
        state = request.app.state
        reference = await _worker(state.operator_auth.authority_reference, token=request.cookies.get(COOKIE), create=False)
        if reference is None:
            return _error(401, 'AUTH_FAILED', 'Sign in as the human operator to detach this presentation.')
        services = _services(state, body.presentation)
        if services is None:
            return _error(409, 'CONFLICT', 'This presentation is currently unavailable.')
        try:
            await _worker(services.broker.detach, scope=body.input_scope(), channel_id=body.channel_id,
                          author=InputAuthor(reference, 'native_terminal'), attachment_id=attachment_id)
        except OktoNexusError as error:
            return _runtime_error(error)
        return JSONResponse({'version': 1, 'state': 'DETACHED'}, headers=_HEADERS)

    return router
