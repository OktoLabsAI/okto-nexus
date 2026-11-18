"""Origin-bound local presenter client for the terminal relay."""

import re
import socket
import ssl
import time
from contextlib import ExitStack, contextmanager, suppress
from ipaddress import ip_address
from select import select
from urllib.parse import quote, urlsplit

from nexus_connector_core.protocol import canonical_json, strict_json
from wsproto import ConnectionType, WSConnection
from wsproto.events import (
    AcceptConnection,
    CloseConnection,
    Ping,
    RejectConnection,
    Request,
    TextMessage,
)
from wsproto.utilities import ProtocolError

from ...application.codex_viewer_protocol import CodexViewerContext
from ...application.terminal_connection import PREFIX, ConnectionError
from ...domain.presentation_protocol import (
    MAX_PRESENTATION_REQUEST_BYTES,
    MAX_PRESENTATION_RESPONSE_BYTES,
    PRESENTATION_SUBPROTOCOL,
)

_HISTORY_METHODS = ('thread/turns/list', 'thread/items/list')
_TIMEOUT = 10


class _LocalPresenter:
    def __init__(self, peer, wire, attachment_id):
        self._peer = peer
        self._wire = wire
        self.attachment_id = attachment_id
        self._request_id = 0

    def close(self):
        """Stop this presentation socket, including an in-flight read."""
        with suppress(OSError):
            self._peer.shutdown(socket.SHUT_RDWR)
        self._peer.close()

    def ensure_open(self):
        """Observe upstream close while the viewer is idle without another request."""
        if self._peer.fileno() < 0:
            raise OSError('The presentation socket closed')
        tls_pending = isinstance(self._peer, ssl.SSLSocket) and self._peer.pending()
        if not tls_pending and not select([self._peer], [], [], 0)[0]:
            return
        self._peer.settimeout(.2)
        try:
            data = self._peer.recv(16 * 1024)
        except TimeoutError:
            return
        if not data:
            raise OSError('The presentation socket closed')
        self._wire.receive_data(data)
        for event in self._wire.events():
            if not isinstance(event, Ping):
                raise OSError('The presentation sent an unsolicited event or closed')
            self._peer.sendall(self._wire.send(event.response()))

    def _events(self, deadline):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Presentation response timed out')
            self._peer.settimeout(remaining)
            data = self._peer.recv(64 * 1024)
            if not data:
                raise OSError('Presentation socket closed')
            self._wire.receive_data(data)
            for event in self._wire.events():
                if isinstance(event, (CloseConnection, RejectConnection)):
                    raise OSError('Presentation socket refused or closed')
                if isinstance(event, Ping):
                    self._peer.sendall(self._wire.send(event.response()))
                else:
                    yield event

    def upgrade(self, *, host, path, headers, ticket):
        self._peer.sendall(self._wire.send(Request(host=host, target=path,
            subprotocols=[PRESENTATION_SUBPROTOCOL], extra_headers=[
                (b'authorization', ('Bearer ' + ticket).encode()),
                (b'cookie', headers['Cookie'].encode()),
                (b'origin', headers['Origin'].encode()),
            ])))
        event = next(self._events(time.monotonic() + _TIMEOUT))
        if not isinstance(event, AcceptConnection) or event.subprotocol != PRESENTATION_SUBPROTOCOL:
            raise ValueError('Presentation subprotocol did not match')

    def exchange(self, frame):
        raw = canonical_json(frame)
        if len(raw) > MAX_PRESENTATION_REQUEST_BYTES:
            raise ValueError('Presentation request too large')
        self._peer.settimeout(_TIMEOUT)
        self._peer.sendall(self._wire.send(TextMessage(data=raw.decode())))
        parts, received = [], 0
        for event in self._events(time.monotonic() + _TIMEOUT):
            if not isinstance(event, TextMessage):
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

    def page(self, *, method, params):
        if method not in _HISTORY_METHODS:
            raise ConnectionError('PRESENTATION_METHOD_UNAVAILABLE', 'Only scoped history can be read on this link.')
        return self._request('page', method=method, params=params)

    def viewer_context(self):
        try:
            return CodexViewerContext.model_validate(self._request('context'))
        except ValueError:
            raise _unavailable() from None

    def _request(self, kind, **payload):
        self._request_id += 1
        try:
            response = self.exchange({'kind': kind, 'request_id': self._request_id, **payload})
            if (response.keys() != {'kind', 'request_id', kind} or response['kind'] != kind
                    or type(response['request_id']) is not int
                    or response['request_id'] != self._request_id
                    or not isinstance(response[kind], dict)):
                raise ValueError('The presentation response did not match the request')
        except (OSError, TypeError, ValueError, ProtocolError, RecursionError):
            raise _unavailable() from None
        return response[kind]


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


def review_local_presentation(api, *, scope, expected_session_generation):
    """Read an exact viewer capability without issuing an attachment ticket."""
    _local_origin(api, scope)
    state = {'scope': dict(scope), 'expected_session_generation': expected_session_generation}
    response = api('POST', PREFIX + '/sessions/' + quote(scope['session_id'], safe='') + '/attachments:review', state)
    revision = response.get('capability_revision')
    if (type(response.get('version')) is not int or response['version'] != 1
            or response.get('attach_strategy') != 'codex_local_read'
            or response.get('scope') != scope or type(response.get('expected_session_generation')) is not int
            or response['expected_session_generation'] != expected_session_generation
            or not isinstance(revision, str) or not 1 <= len(revision) <= 160 or not revision.isprintable()):
        raise _unavailable()
    return revision


@contextmanager
def open_local_presentation(api, *, scope, expected_session_generation, capability_revision, client_intent_id):
    """Exchange the offer and challenge without passing the human session to the viewer."""
    origin = _local_origin(api, scope)
    port = origin.port or (443 if origin.scheme == 'https' else 80)
    host = origin.hostname
    state = {'scope': dict(scope), 'expected_session_generation': expected_session_generation}
    offer = api('POST', PREFIX + '/sessions/' + quote(scope['session_id'], safe='') + '/attachments:prepare',
        state | {'capability_revision': capability_revision, 'client_intent_id': client_intent_id,
                 'intent': 'attach_live', 'access': 'read'})
    attachment_id, ticket = offer.get('attachment_id'), offer.get('ticket')
    if (type(offer.get('version')) is not int or offer['version'] != 1 or offer.get('state') != 'PREPARED'
            or not isinstance(attachment_id, str) or not re.fullmatch(r'att_[0-9a-f]{32}', attachment_id)
            or not isinstance(ticket, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', ticket)):
        raise _unavailable()
    with ExitStack() as stack:
        try:
            peer = stack.enter_context(socket.create_connection((host, port), timeout=_TIMEOUT))
            if not ip_address(peer.getpeername()[0]).is_loopback:
                raise ValueError('The presentation peer is not local')
            if origin.scheme == 'https':
                peer = stack.enter_context(ssl.create_default_context().wrap_socket(peer, server_hostname=host))
            link = _LocalPresenter(peer, WSConnection(ConnectionType.CLIENT), attachment_id)
            link.upgrade(host=origin.netloc, path=PREFIX + f'/attachments/{attachment_id}/stream',
                         headers=api.request_headers(), ticket=ticket)
            challenge = link.exchange({'kind': 'hello', 'version': 1, **state})
            nonce = challenge.get('challenge')
            if (challenge.get('kind') != 'challenge' or not isinstance(nonce, str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{43}', nonce)):
                raise ValueError('Invalid presentation challenge')
            result = link.exchange({'kind': 'prove', 'challenge': nonce})
            if result != {'kind': 'attached', 'attachment_id': attachment_id, 'access': 'read'}:
                raise ValueError('Invalid presentation receipt')
        except (OSError, TypeError, ValueError, ProtocolError, RecursionError):
            raise _unavailable() from None
        yield link
