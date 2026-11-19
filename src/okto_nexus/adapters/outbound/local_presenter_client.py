"""Origin-bound local presenter client for the terminal relay."""

import re
import socket
import ssl
import time
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
from ipaddress import ip_address
from select import select
from urllib.parse import quote, urlsplit

from nexus_connector_core.protocol import canonical_json, strict_json
from wsproto import ConnectionType, WSConnection
from wsproto.events import (
    AcceptConnection,
    BytesMessage,
    CloseConnection,
    Ping,
    RejectConnection,
    Request,
    TextMessage,
)
from wsproto.utilities import ProtocolError

from ...application.codex_viewer_protocol import (
    CodexInputStatus,
    CodexPendingInput,
    CodexPendingInterrupt,
    CodexViewerContext,
)
from ...application.terminal_connection import PREFIX, ConnectionError
from ...domain.presentation_protocol import (
    MAX_PRESENTATION_NOTIFICATIONS,
    MAX_PI_PRESENTATION_BYTES,
    MAX_PRESENTATION_REQUEST_BYTES,
    MAX_PRESENTATION_RESPONSE_BYTES,
    PRESENTATION_SUBPROTOCOL,
    PI_PRESENTATION_SUBPROTOCOL,
)
from ...domain.session_interaction import MAX_SQLITE_INTEGER, InputDeliveryState

_HISTORY_METHODS = ('thread/turns/list', 'thread/items/list')
_TIMEOUT = 10


@dataclass(frozen=True, slots=True)
class LocalWriterReview:
    capability_revision: str
    input_revision: str
    epoch: int
    occupied: bool


class _LocalPresenter:
    def __init__(self, peer, wire, attachment_id, *, live_updates, input_revision=None):
        self._peer = peer
        self._wire = wire
        self.attachment_id = attachment_id
        self.live_updates = live_updates
        self.input_revision = input_revision
        self._request_id = 0

    def close(self):
        """Stop this presentation socket, including an in-flight read."""
        with suppress(OSError):
            self._peer.shutdown(socket.SHUT_RDWR)
        self._peer.close()

    def ensure_open(self):
        """Observe upstream close while the viewer is idle without another request."""
        if self._peer.fileno() < 0:
            raise _unavailable()
        tls_pending = isinstance(self._peer, ssl.SSLSocket) and self._peer.pending()
        if not tls_pending and not select([self._peer], [], [], 0)[0]:
            return
        self._peer.settimeout(.2)
        try:
            data = self._peer.recv(16 * 1024)
        except TimeoutError:
            return
        if not data:
            raise _unavailable()
        self._wire.receive_data(data)
        for event in self._wire.events():
            if not isinstance(event, Ping):
                raise _unavailable()
            self._peer.sendall(self._wire.send(event.response()))

    def _events(self, deadline):
        while True:
            for event in self._wire.events():
                if isinstance(event, (CloseConnection, RejectConnection)):
                    raise OSError('Presentation socket refused or closed')
                if isinstance(event, Ping):
                    self._peer.sendall(self._wire.send(event.response()))
                else:
                    yield event
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Presentation response timed out')
            self._peer.settimeout(remaining)
            data = self._peer.recv(64 * 1024)
            if not data:
                raise OSError('Presentation socket closed')
            self._wire.receive_data(data)

    def upgrade(self, *, host, path, headers, ticket, protocol=PRESENTATION_SUBPROTOCOL):
        self._peer.sendall(self._wire.send(Request(host=host, target=path,
            subprotocols=[protocol], extra_headers=[
                (b'authorization', ('Bearer ' + ticket).encode()),
                (b'cookie', headers['Cookie'].encode()),
                (b'origin', headers['Origin'].encode()),
            ])))
        event = next(self._events(time.monotonic() + _TIMEOUT))
        if not isinstance(event, AcceptConnection) or event.subprotocol != protocol:
            raise ValueError('Presentation subprotocol did not match')

    def exchange(self, frame, *, pi_output=None):
        raw = canonical_json(frame)
        if len(raw) > MAX_PRESENTATION_REQUEST_BYTES:
            raise ValueError('Presentation request too large')
        self._peer.settimeout(_TIMEOUT)
        self._peer.sendall(self._wire.send(TextMessage(data=raw.decode())))
        parts, received = [], 0
        binary = bytearray()
        for event in self._events(time.monotonic() + _TIMEOUT):
            if pi_output is not None and isinstance(event, BytesMessage) and not parts:
                if output := _pi_fragment(binary, event):
                    pi_output(output)
                    binary.clear()
                continue
            if not isinstance(event, TextMessage) or binary:
                raise TypeError('Unexpected presentation response')
            received += len(event.data.encode())
            if received > MAX_PRESENTATION_RESPONSE_BYTES:
                raise ValueError('Presentation response too large')
            parts.append(event.data)
            if event.message_finished:
                value = strict_json(''.join(parts))
                if not isinstance(value, dict):
                    raise ValueError('Invalid presentation response')
                return value
        raise OSError('The presentation response ended early')

    def read_pi_output(self) -> bytes:
        """Read a bounded binary frame with idle waits interruptible by the terminal."""
        data = bytearray()
        while True:
            try:
                for event in self._events(time.monotonic() + 1):
                    if output := _pi_fragment(data, event):
                        return output
            except TimeoutError:
                continue
            except (OSError, ValueError, ProtocolError):
                raise _unavailable() from None

    def send_pi_input(self, *, intent, text, output):
        """Record plain text on the canonical queue while rendering concurrent output."""
        if self.input_revision is None:
            raise ConnectionError('PRESENTATION_MODE_UNAVAILABLE', 'This Pi view is read-only.')
        try:
            receipt = self._request('enqueue', flat=True, pi_output=output, client_intent_id=intent,
                                    capability_revision=self.input_revision, content={'type': 'text', 'text': text})
            input_id = receipt['input_id']
            status = InputDeliveryState(receipt['status'])
            sequence = receipt['enqueue_sequence']
            operation_id = receipt['operation_id']
            if (not isinstance(input_id, str) or not re.fullmatch(r'sin_[0-9a-f]{32}', input_id)
                    or type(sequence) is not int or sequence < 1 or type(receipt['possible_effect']) is not bool
                    or operation_id is not None and (not isinstance(operation_id, str) or not operation_id)):
                raise ValueError
        except (ConnectionError, KeyError, ValueError):
            raise ConnectionError('OUTCOME_UNKNOWN',
                'The queue receipt is unconfirmed. Recover the same message intent before sending again.',
                possible_effect=True) from None
        return {'input_id': input_id, 'status': status, 'enqueue_sequence': sequence,
                'operation_id': operation_id, 'possible_effect': receipt['possible_effect']}

    def page(self, *, method, params):
        if method not in _HISTORY_METHODS:
            raise ConnectionError('PRESENTATION_METHOD_UNAVAILABLE', 'Only scoped history can be read on this link.')
        return self._request('page', method=method, params=params)

    def viewer_context(self):
        try:
            options = {'follow': True} if self.live_updates else {}
            return CodexViewerContext.model_validate(self._request('context', **options))
        except ValueError:
            raise _unavailable() from None

    def updates(self, thread_id):
        data = self._request('updates')
        notifications = data.get('notifications')
        if (data.keys() != {'notifications', 'has_more'} or type(data['has_more']) is not bool
                or not isinstance(notifications, list) or len(notifications) > MAX_PRESENTATION_NOTIFICATIONS):
            raise _unavailable()
        for notification in notifications:
            if (not isinstance(notification, dict) or notification.keys() != {'method', 'params'}
                    or notification['method'] not in ('turn/started', 'turn/completed', 'item/completed')
                    or not isinstance(notification['params'], dict) or notification['params'].get('threadId') != thread_id):
                raise _unavailable()
        return notifications

    def send_next_turn(self, *, thread_id, intent, text):
        """Queue the source intent and keep the native response pending."""
        try:
            queued = self._request('enqueue', flat=True, thread_id=thread_id, client_intent_id=intent,
                capability_revision=self.input_revision, content={'type': 'text', 'text': text})
            input_id = queued.get('input_id')
            if not isinstance(input_id, str) or not re.fullmatch(r'sin_[0-9a-f]{32}', input_id):
                raise _unavailable()
        except ConnectionError:
            return CodexPendingInput(None, 'Delivery is unconfirmed. Check the Nexus session queue before sending again.')

        return CodexPendingInput(input_id, 'Message recorded in the Nexus session queue. Delivery confirmation is pending.')

    def confirm_input_delivery(self, input_id):
        try:
            delivery = self._request('input_delivery', input_id=input_id)
            if delivery.keys() != {'input_id', 'status', 'turn'} or delivery['input_id'] != input_id:
                raise _unavailable()
            status = InputDeliveryState(delivery['status'])
        except (ConnectionError, ValueError):
            raise CodexInputStatus('Message recorded. Check its delivery in the Nexus session queue.') from None
        if status not in {InputDeliveryState.QUEUED, InputDeliveryState.DISPATCHING, InputDeliveryState.ACCEPTED_NATIVE}:
            raise CodexInputStatus('Message recorded. Check its delivery in the Nexus session queue.')
        turn = delivery['turn']
        if status is not InputDeliveryState.QUEUED and isinstance(turn, dict):
            return turn
        return None

    def _review_turn(self, action, *, thread_id, turn_id, intent, **payload):
        try:
            review = self._request(action + '_review', thread_id=thread_id, turn_id=turn_id,
                                  client_intent_id=intent, **payload)
        except ConnectionError:
            raise CodexInputStatus('The exact turn review is unavailable.') from None
        review_id = review.get('review_id')
        if (not isinstance(review_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32}', review_id)
                or review.get('turn_id') != turn_id):
            raise CodexInputStatus('The selected turn is unavailable for this control.')
        return review_id

    def steer(self, *, thread_id, turn_id, intent, text, confirm):
        review_id = self._review_turn('steer', thread_id=thread_id, turn_id=turn_id, intent=intent,
                                      content={'type': 'text', 'text': text})
        if not confirm(turn_id, text):
            raise CodexInputStatus('Reorientation cancelled.')
        try:
            result = self._request('steer_confirm', review_id=review_id)
        except ConnectionError:
            return CodexPendingInput(None, 'Reorientation is unconfirmed. Check the Nexus session before trying again.')
        if result.get('status') == 'refused':
            raise CodexInputStatus('The reorientation review is no longer valid. Your message was not sent.')
        input_id = result.get('input_id')
        if result.get('status') != 'recorded' or not isinstance(input_id, str) or not re.fullmatch(r'sin_[0-9a-f]{32}', input_id):
            return CodexPendingInput(None, 'Reorientation is unconfirmed. Check the Nexus session before trying again.')
        return CodexPendingInput(input_id, 'Reorientation recorded for the selected turn. Native confirmation is pending.',
                                 steer_target=turn_id)

    def confirm_steer_delivery(self, input_id):
        try:
            result = self._request('input_delivery', input_id=input_id)
            if result.get('input_id') != input_id:
                raise _unavailable()
            status = InputDeliveryState(result['status'])
        except (ConnectionError, KeyError, ValueError):
            raise CodexInputStatus('Reorientation recorded. Check the Nexus session for its delivery status.') from None
        if status in (InputDeliveryState.QUEUED, InputDeliveryState.DISPATCHING):
            return False
        if status is InputDeliveryState.ACCEPTED_NATIVE:
            return True
        raise CodexInputStatus('Reorientation recorded. Check the Nexus session for its delivery status.')

    def interrupt(self, *, thread_id, turn_id, intent, confirm):
        review_id = self._review_turn('interrupt', thread_id=thread_id, turn_id=turn_id, intent=intent)
        if not confirm(turn_id):
            raise CodexInputStatus('Interruption cancelled.')
        message = 'Interruption is unconfirmed. Check the Nexus session and its queue before trying again.'
        try:
            result = self._request('interrupt_confirm', review_id=review_id)
        except ConnectionError:
            return CodexPendingInterrupt(intent, message)
        if result == {'status': 'refused'}:
            raise CodexInputStatus('The interrupt review is no longer valid. This request did not interrupt the turn.')
        if result == {'status': 'recorded'}:
            message = 'Interruption recorded. The queue is paused while the selected turn is checked.'
        return CodexPendingInterrupt(intent, message)

    def confirm_interrupt(self, *, thread_id, intent):
        try:
            result = self._request('interrupt_receipt', thread_id=thread_id, client_intent_id=intent)
        except ConnectionError:
            raise CodexInputStatus('Interruption is unconfirmed. Check the Nexus session and its queue.') from None
        if result.get('target_status') == 'interrupted' and result.get('refused') is False:
            return True
        if result.get('target_status') == 'finished' and result.get('refused') is False:
            raise CodexInputStatus('The selected turn finished. Check the queue before resuming it.')
        if result.get('refused') is True:
            raise CodexInputStatus('The interruption was refused. Check the queue before resuming it.')
        return False

    def _request(self, kind, *, flat=False, pi_output=None, **payload):
        self._request_id += 1
        try:
            frame = {'kind': kind, 'request_id': self._request_id, **payload}
            response = self.exchange(frame) if pi_output is None else self.exchange(frame, pi_output=pi_output)
            if (response.get('kind') != kind or type(response.get('request_id')) is not int
                    or response['request_id'] != self._request_id):
                raise ValueError('The presentation response did not match the request')
            if flat:
                return response
            if response.keys() != {'kind', 'request_id', kind} or not isinstance(response[kind], dict):
                raise ValueError('The presentation response did not match the request')
        except (OSError, TypeError, ValueError, ProtocolError, RecursionError):
            raise _unavailable() from None
        return response[kind]


def _pi_fragment(data, event):
    if not isinstance(event, BytesMessage) or len(data) + len(event.data) > MAX_PI_PRESENTATION_BYTES:
        raise ValueError('Invalid Pi renderer frame')
    data.extend(event.data)
    if event.message_finished:
        if not data:
            raise ValueError('Empty Pi renderer frame')
        return bytes(data)
    return None


def _unavailable():
    return ConnectionError('PRESENTATION_UNAVAILABLE', 'The local presentation could not be confirmed. Review the exact session again.')


def _local_origin(api, scope):
    expected_keys = {'server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id',
                     'agent_id', 'session_id'}
    if (scope.keys() != expected_keys or not getattr(api, 'server_id', None) or scope['server_id'] != api.server_id
            or not getattr(api, 'token', None) or not all(isinstance(value, str) and value for value in scope.values())):
        raise _unavailable()
    origin = urlsplit(api.base)
    host = origin.hostname
    if origin.scheme not in ('http', 'https') or host not in ('localhost', '127.0.0.1', '::1'):
        raise ConnectionError('PRESENTATION_LOCAL_REQUIRED', 'This presentation requires the local Server address.')
    return origin


def _revision(value):
    return isinstance(value, str) and 1 <= len(value) <= 160 and value.isprintable()


def review_local_presentation(api, *, scope, expected_session_generation, write=False, presentation='codex'):
    """Read an exact viewer capability without issuing an attachment ticket."""
    _local_origin(api, scope)
    state = {'scope': dict(scope), 'expected_session_generation': expected_session_generation}
    if presentation == 'pi':
        state['presentation'] = 'pi'
    if write:
        state['access'] = 'write'
    try:
        response = api('POST', PREFIX + '/sessions/' + quote(scope['session_id'], safe='') + '/attachments:review', state)
    except ConnectionError as error:
        if error.http_status in (404, 405) and not error.possible_effect:
            raise ConnectionError('PRESENTATION_UNAVAILABLE',
                'The selected Server does not offer native presentation for this session.',
                http_status=error.http_status) from None
        raise
    revision = response.get('capability_revision')
    if (type(response.get('version')) is not int or response['version'] != 1
            or response.get('attach_strategy') != f"{presentation}_local_{'write' if write else 'read'}"
            or response.get('scope') != scope or type(response.get('expected_session_generation')) is not int
            or response['expected_session_generation'] != expected_session_generation
            or not _revision(revision)):
        raise _unavailable()
    if write:
        epoch, occupied = response.get('writer_epoch'), response.get('writer_occupied')
        input_revision = response.get('input_capability_revision')
        if (type(epoch) is not int or not 0 <= epoch < MAX_SQLITE_INTEGER or type(occupied) is not bool
                or not _revision(input_revision)):
            raise _unavailable()
        return LocalWriterReview(revision, input_revision, epoch, occupied)
    return revision


@contextmanager
def open_local_presentation(api, *, scope, expected_session_generation, capability_revision, client_intent_id,
                            writer=None, pi_viewport=None):
    """Exchange the offer and challenge without passing the human session to the viewer."""
    origin = _local_origin(api, scope)
    port = origin.port or (443 if origin.scheme == 'https' else 80)
    host = origin.hostname
    state = {'scope': dict(scope), 'expected_session_generation': expected_session_generation}
    access = 'write' if writer is not None else 'read'
    writer_fields = {'expected_writer_epoch': writer.epoch, 'takeover': writer.occupied} if writer is not None else {}
    pi_fields = {'presentation': 'pi'} if pi_viewport is not None else {}
    offer = api('POST', PREFIX + '/sessions/' + quote(scope['session_id'], safe='') + '/attachments:prepare',
        state | {'capability_revision': capability_revision, 'client_intent_id': client_intent_id,
                 'intent': 'attach_live', 'access': access} | writer_fields | pi_fields)
    attachment_id, ticket = offer.get('attachment_id'), offer.get('ticket')
    live_updates = offer.get('live_updates', False)
    if (type(offer.get('version')) is not int or offer['version'] != 1 or offer.get('state') != 'PREPARED'
            or not isinstance(attachment_id, str) or not re.fullmatch(r'att_[0-9a-f]{32}', attachment_id)
            or not isinstance(ticket, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', ticket)
            or type(live_updates) is not bool):
        raise _unavailable()
    with ExitStack() as stack:
        try:
            peer = stack.enter_context(socket.create_connection((host, port), timeout=_TIMEOUT))
            if not ip_address(peer.getpeername()[0]).is_loopback:
                raise ValueError('The presentation peer is not local')
            if origin.scheme == 'https':
                peer = stack.enter_context(ssl.create_default_context().wrap_socket(peer, server_hostname=host))
            link = _LocalPresenter(peer, WSConnection(ConnectionType.CLIENT), attachment_id,
                                   live_updates=live_updates, input_revision=writer.input_revision if writer else None)
            link.upgrade(host=origin.netloc, path=PREFIX + f'/attachments/{attachment_id}/stream',
                         headers=api.request_headers(), ticket=ticket,
                         protocol=PI_PRESENTATION_SUBPROTOCOL if pi_viewport is not None else PRESENTATION_SUBPROTOCOL)
            viewport = dict(zip(('columns', 'rows'), pi_viewport, strict=True)) if pi_viewport is not None else {}
            challenge = link.exchange({'kind': 'hello', 'version': 1, **state, **viewport})
            nonce = challenge.get('challenge')
            if (challenge.get('kind') != 'challenge' or not isinstance(nonce, str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{43}', nonce)):
                raise ValueError('Invalid presentation challenge')
            result = link.exchange({'kind': 'prove', 'challenge': nonce})
            if result != {'kind': 'attached', 'attachment_id': attachment_id, 'access': access}:
                raise ValueError('Invalid presentation receipt')
        except (OSError, TypeError, ValueError, ProtocolError, RecursionError):
            raise _unavailable() from None
        yield link
