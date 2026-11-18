"""One loopback terminal viewer on a separate authenticated Server link."""

import hmac
import secrets
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from nexus_connector_core.protocol import canonical_json, strict_json
from wsproto import ConnectionType, WSConnection
from wsproto.events import (
    AcceptConnection,
    CloseConnection,
    Ping,
    Pong,
    RejectConnection,
    Request,
    TextMessage,
)
from wsproto.utilities import ProtocolError

from ....application.codex_viewer_protocol import CodexViewerProtocol
from ....application.terminal_connection import ConnectionError
from ....domain.presentation_protocol import (
    MAX_PRESENTATION_REQUEST_BYTES,
    MAX_PRESENTATION_RESPONSE_BYTES,
)

_CONNECT_SECONDS = 30
_FRAME_SECONDS = 5
_POLL_SECONDS = .2
_UPDATE_SECONDS = .5


@dataclass(frozen=True, slots=True)
class CodexRelayEndpoint:
    address: str
    token: str = field(repr=False)
    thread_id: str
    connected: threading.Event = field(repr=False, compare=False)


def _receive_events(peer, wire, stop, deadline, idle=None):
    while not stop.is_set():
        expires = deadline()
        if expires is not None and time.monotonic() >= expires:
            raise TimeoutError('Incomplete viewer frame')
        try:
            data = peer.recv(16 * 1024)
        except TimeoutError:
            if idle is not None:
                idle()
            continue
        if not data:
            return
        wire.receive_data(data)
        yield from wire.events()


def _accepted(event, host, secret):
    if (not isinstance(event, Request) or event.host != host or event.target != '/'
            or event.subprotocols or any(name.lower() == b'origin' for name, _ in event.extra_headers)):
        return False
    values = [value for name, value in event.extra_headers if name.lower() == b'authorization']
    return len(values) == 1 and hmac.compare_digest(values[0], secret)


def _reply(peer, wire, frame):
    text = canonical_json(frame)
    if len(text) > MAX_PRESENTATION_RESPONSE_BYTES:
        raise ValueError('Viewer response too large')
    peer.sendall(wire.send(TextMessage(data=text.decode())))


def _notice(peer, wire, frame):
    params = frame['params']
    item = params.get('item')
    if (frame['method'] == 'item/completed' and isinstance(item, dict)
            and item.get('type') == 'agentMessage' and all(isinstance(value, str) for value in (
                item.get('text'), item.get('id'), params.get('turnId')))):
        # This viewer paints assistant text on its delta notification. Send
        # the whole scrubbed completion once instead of forwarding raw chunks.
        _reply(peer, wire, {'jsonrpc': '2.0', 'method': 'item/agentMessage/delta', 'params': {
            'threadId': params['threadId'], 'turnId': params['turnId'],
            'itemId': item['id'], 'delta': item['text']}})
    _reply(peer, wire, {'jsonrpc': '2.0', **frame})


def _viewer(peer, wire, protocol, stop, link):
    parts, size, deadline = [], 0, None
    next_update = 0.0

    def follow():
        nonlocal next_update
        link.ensure_open()
        if (deadline is not None or not getattr(link, 'live_updates', False) or not protocol.following
                or time.monotonic() < next_update):
            return
        next_update = time.monotonic() + _UPDATE_SECONDS
        for frame in link.updates(protocol.context.thread_id):
            if stop.is_set():
                return
            _notice(peer, wire, frame)

    events = _receive_events(peer, wire, stop, lambda: deadline, follow)
    for event in events:
        if stop.is_set():
            return
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError('Incomplete viewer frame')
        if isinstance(event, CloseConnection):
            peer.sendall(wire.send(event.response()))
            return
        if isinstance(event, Ping):
            peer.sendall(wire.send(event.response()))
            continue
        if isinstance(event, Pong):
            continue
        if not isinstance(event, TextMessage):
            raise TypeError('Unexpected viewer frame')
        size += len(event.data.encode())
        if size > MAX_PRESENTATION_REQUEST_BYTES:
            raise ValueError('Viewer request too large')
        if event.data:
            parts.append(event.data)
        if not event.message_finished:
            deadline = deadline or time.monotonic() + _FRAME_SECONDS
            continue
        link.ensure_open()
        response = protocol.handle(strict_json(''.join(parts)))
        if response is not None:
            _reply(peer, wire, response)
        if protocol.detached:
            peer.sendall(wire.send(CloseConnection(code=1000)))
            return
        parts, size, deadline = [], 0, None
        follow()


def _serve_once(listener, *, host, secret, protocol, stop, link, connected):
    expires = time.monotonic() + _CONNECT_SECONDS
    while not stop.is_set() and time.monotonic() < expires:
        try:
            peer, _ = listener.accept()
        except TimeoutError:
            continue
        with peer:
            peer.settimeout(_POLL_SECONDS)
            wire = WSConnection(ConnectionType.SERVER)
            deadline = min(expires, time.monotonic() + _FRAME_SECONDS)
            handshake = _receive_events(peer, wire, stop, lambda deadline=deadline: deadline)
            try:
                offer = next(handshake, None)
                if not _accepted(offer, host, secret):
                    if isinstance(offer, Request):
                        peer.sendall(wire.send(RejectConnection(status_code=403)))
                    continue
                peer.sendall(wire.send(AcceptConnection()))
                connected.set()
            except (OSError, ProtocolError, ValueError):
                continue
            listener.close()
            try:
                _viewer(peer, wire, protocol, stop, link)
            except (ConnectionError, OSError, ProtocolError, RecursionError, TypeError, ValueError):
                return
            return


@contextmanager
def local_codex_relay(link, *, viewer_home, platform_os):
    """Own one loopback socket and its Server link. The viewer gets its own secret."""
    context = link.viewer_context()
    with socket.create_server(('127.0.0.1', 0), backlog=2) as listener:
        listener.settimeout(_POLL_SECONDS)
        host = f'127.0.0.1:{listener.getsockname()[1]}'
        token = secrets.token_urlsafe(32)
        stop = threading.Event()
        connected = threading.Event()
        protocol = CodexViewerProtocol(context=context, read_page=link.page, viewer_home=viewer_home,
                                       platform_os=platform_os)

        def serve():
            try:
                _serve_once(listener, host=host, secret=('Bearer ' + token).encode(), protocol=protocol,
                            stop=stop, link=link, connected=connected)
            finally:
                link.close()

        worker = threading.Thread(target=serve, name='nexus-codex-viewer', daemon=True)
        worker.start()
        try:
            yield CodexRelayEndpoint('ws://' + host, token, context.thread_id, connected)
        finally:
            stop.set()
            link.close()
            worker.join(2)
            if worker.is_alive():
                raise RuntimeError('The local Codex viewer relay did not quit.')
