"""Exercise the local presentation protocol across HTTP and WebSocket."""

import json
from contextlib import asynccontextmanager
import socket
import threading
import time
from dataclasses import asdict, replace
from types import SimpleNamespace
from urllib.parse import urlsplit

import anyio
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from wsproto import ConnectionType, WSConnection
from wsproto.events import AcceptConnection, RejectConnection, Request, TextMessage

from okto_nexus.adapters.inbound.cli.codex_viewer_relay import local_codex_relay
from okto_nexus.adapters.inbound.http import dashboard_session_presentations
from okto_nexus.adapters.inbound.http.operator_auth import COOKIE, OperatorAuth
from okto_nexus.adapters.inbound.http.session_interaction_contract import (
    InterruptTargetView,
    NativeTurnTarget,
    ObservedRunTarget,
    SteerTargetView,
)
from okto_nexus.adapters.outbound.local_presenter_client import (
    _LocalPresenter,
    open_local_presentation,
    review_local_presentation,
)
from okto_nexus.adapters.outbound.operator_client import RemoteOperatorHTTP
from okto_nexus.application import (
    codex_presenter_channel,
    session_interaction_authority,
)
from okto_nexus.application.codex_presenter_history import CodexHistorySnapshot
from okto_nexus.application.codex_viewer_protocol import (
    CodexPendingInput,
    CodexPendingInterrupt,
    CodexViewerContext,
    CodexViewerProtocol,
)
from okto_nexus.application.session_attachment_broker import SessionAttachmentBroker
from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus.application.execution_native_session_mapping import (
    _PI_PRESENTATION_BUILD, ManagedNativeSession, NativeLaunchBuild,
)
from okto_nexus.bootstrap import local_pi_presentations
from okto_nexus.bootstrap.local_pi_presentations import publish_local_pi_presentations
from okto_nexus.domain.presentation_protocol import CLAUDE_PRESENTATION_SUBPROTOCOL, PI_PRESENTATION_SUBPROTOCOL
from okto_nexus.domain.session_interaction import InputAuthor
from tests.session_interaction.test_queue_storage import database as queue_database
from tests.session_interaction.test_queue_storage import enqueue

database = queue_database
THREAD = 'bdfe5b81-54cf-43cf-8001-5de670d3dd69'
PREFIX = '/api/v1/runtime-management'
SUBPROTOCOL = 'nexus.presenter.v1'
ORIGIN = 'http://127.0.0.1'


def viewer_context(path):
    return CodexViewerContext(thread_id=THREAD, session_id=THREAD, cwd=str(path), model='synthetic',
        model_provider='openai', status='idle', created_at=1, updated_at=2, ephemeral=True, cli_version='0.170.0',
        source='cli', approval_policy='never', approvals_reviewer='user',
        sandbox={'type': 'readOnly', 'networkAccess': False}, reasoning_effort='medium')


def next_event(peer, wire):
    yield from wire.events()
    while data := peer.recv(64 * 1024):
        wire.receive_data(data)
        yield from wire.events()


def open_viewer(endpoint, peer, *, token, extra=()):
    host = urlsplit(endpoint.address).netloc
    wire = WSConnection(ConnectionType.CLIENT)
    peer.sendall(wire.send(Request(host=host, target='/',
        extra_headers=[(b'authorization', ('Bearer ' + token).encode()), *extra])))
    return wire


def rpc(peer, wire, ident, method, **params):
    peer.sendall(wire.send(TextMessage(data=json.dumps({'id': ident, 'method': method, 'params': params}))))
    fragments = []
    for event in next_event(peer, wire):
        assert isinstance(event, TextMessage)
        fragments.append(event.data)
        if event.message_finished:
            return json.loads(''.join(fragments))
    pytest.fail('The viewer closed before returning a reply')


@pytest.fixture
def transport(database, tmp_path, monkeypatch):
    factory, (scope, sibling) = database
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lease_state='ACTIVE'")
    auth = OperatorAuth(tmp_path / 'auth')
    assert auth.configure('test-operator', 'synthetic-local-operator-password', local=True)
    token = auth.login('test-operator', 'synthetic-local-operator-password')
    another_token = auth.login('test-operator', 'synthetic-local-operator-password')
    auth.authority_reference(another_token)
    app = FastAPI()
    app.state.deps = SimpleNamespace(
        config=SimpleNamespace(transport_security='http_https'),
        runtime_availability=SimpleNamespace(current_host=lambda *_: None),
    )
    app.state.operator_auth = auth
    broker = SessionAttachmentBroker(factory, authority_fence=auth.authority_fence,
        current_capability=lambda *_: 'capability-1')

    async def prove(requested):
        assert requested == scope
        return SimpleNamespace(codex_thread_id=THREAD), 'same-owner'

    async def context(requested):
        assert requested == scope
        return viewer_context(tmp_path)

    monkeypatch.setattr(codex_presenter_channel, 'read_codex_history_snapshot',
                        lambda *_args, **_kwargs: CodexHistorySnapshot(0, 0, (), ()))
    app.state.local_codex_presentations = dashboard_session_presentations.LocalCodexPresentations(
        broker, prove, object(), read_context=context)
    app.include_router(dashboard_session_presentations.build_router(), prefix=PREFIX)
    with TestClient(app, base_url=ORIGIN, client=('127.0.0.1', 12345)) as client:
        client.cookies.set(COOKIE, token)
        yield SimpleNamespace(client=client, app=app, auth=auth, token=token, other=another_token,
                              factory=factory, scope=scope, sibling=sibling)


def document(scope):
    return {'scope': {**asdict(scope.session), 'binding_id': scope.binding_id, 'workspace_id': scope.workspace_id,
                      'workspace_binding_id': scope.workspace_binding_id, 'agent_id': scope.agent_id},
            'expected_session_generation': scope.generation.value}


def prepare(transport, client_intent_id='exact-view', **extra):
    return transport.client.post(PREFIX + f'/sessions/{transport.scope.session.session_id}/attachments:prepare',
        headers={'x-nexus-ui': '1'}, json={**document(transport.scope), 'capability_revision': 'capability-1',
        'client_intent_id': client_intent_id, 'intent': 'attach_live', 'access': 'read', **extra})


def stream(transport, offer, *, path='', protocol=SUBPROTOCOL, **headers):
    return transport.client.websocket_connect('ws://127.0.0.1' + PREFIX + '/attachments/'
        + offer['attachment_id'] + '/stream' + path,
        headers={'Authorization': 'Bearer ' + offer['ticket'], **headers}, subprotocols=[protocol])


def hello(ws, scope):
    ws.send_json({'kind': 'hello', 'version': 1, **document(scope)})


def attach(ws, scope):
    hello(ws, scope)
    challenge = ws.receive_json()
    assert challenge['kind'] == 'challenge'
    ws.send_json({'kind': 'prove', 'challenge': challenge['challenge']})
    assert ws.receive_json()['kind'] == 'attached'
    return challenge['channel_id']


def attachment_state(transport, offer):
    with transport.factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("""SELECT state,ticket_hash,challenge_hash
          FROM session_attachments WHERE attachment_id=?""", (offer['attachment_id'],)).fetchone()
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
        return tuple(row)


def test_claude_terminal_reader_detaches_and_refuses_input(transport):
    readers = []

    async def prove(scope):
        assert scope == transport.scope
        return SimpleNamespace(adapter_id='claude_stream'), 'same-owned-terminal'

    @asynccontextmanager
    async def open_reader(scope):
        assert scope == transport.scope
        readers.append('opened')

        async def output():
            yield b'Marker from the existing terminal\r\n'
            await anyio.sleep_forever()

        try:
            yield output()
        finally:
            readers.append('detached')

    broker = transport.app.state.local_codex_presentations.broker
    transport.app.state.local_claude_presentations = dashboard_session_presentations.LocalClaudePresentations(
        broker, prove, open_reader)
    review = transport.client.post(PREFIX + f'/sessions/{transport.scope.session.session_id}/attachments:review',
        headers={'x-nexus-ui': '1'}, json=document(transport.scope) | {'presentation': 'claude'})
    assert review.status_code == 200 and review.json()['attach_strategy'] == 'claude_local_read'
    refused = prepare(transport, presentation='claude', access='write', expected_writer_epoch=0)
    assert refused.status_code == 409

    first = prepare(transport, presentation='claude').json()
    with stream(transport, first, protocol=CLAUDE_PRESENTATION_SUBPROTOCOL) as ws:
        attach(ws, transport.scope)
        assert ws.receive_bytes() == b'Marker from the existing terminal\r\n'
    assert attachment_state(transport, first) == ('DETACHED', None, None)

    second = prepare(transport, 'second-claude-reader', presentation='claude').json()
    with stream(transport, second, protocol=CLAUDE_PRESENTATION_SUBPROTOCOL) as ws:
        attach(ws, transport.scope)
        assert ws.receive_bytes().startswith(b'Marker from')
        ws.send_bytes(b'/exit\r')
        with pytest.raises(WebSocketDisconnect):
            ws.receive_bytes()
    assert readers == ['opened', 'detached', 'opened', 'detached']
    assert attachment_state(transport, second) == ('DETACHED', None, None)


def test_authenticated_read_disconnect_and_replay_leave_work_untouched(transport):
    prepared = prepare(transport)
    assert prepared.status_code == 201 and prepared.headers['cache-control'] == 'no-store'
    offer = prepared.json()
    replay = prepare(transport)
    assert replay.status_code == 200 and replay.json()['ticket'] is None
    with stream(transport, offer) as ws:
        attach(ws, transport.scope)
        ws.send_json({'kind': 'page', 'request_id': 1, 'method': 'thread/items/list', 'params': {'threadId': THREAD}})
        assert ws.receive_json() == {'kind': 'page', 'request_id': 1,
            'page': {'data': [], 'nextCursor': None, 'backwardsCursor': None}}
    assert attachment_state(transport, offer) == ('DETACHED', None, None)
    with stream(transport, offer) as ws, pytest.raises(WebSocketDisconnect):
        hello(ws, transport.scope)
        ws.receive_json()


def test_origin_ticket_scope_and_human_are_checked_before_challenge(transport):
    offer = prepare(transport).json()
    for path, headers in (('', {'Origin': 'http://example.test'}), ('?extra=1', {}),
                          ('', {'x-forwarded-for': '127.0.0.1'}), ('', {'Authorization': 'Bearer invalid'})):
        with pytest.raises(WebSocketDisconnect), stream(transport, offer, path=path, **headers):
            pytest.fail('The upgrade should be refused')
    with stream(transport, offer) as ws, pytest.raises(WebSocketDisconnect):
        hello(ws, transport.sibling)
        ws.receive_json()
    transport.client.cookies.set(COOKIE, transport.other)
    with stream(transport, offer) as ws, pytest.raises(WebSocketDisconnect):
        hello(ws, transport.scope)
        ws.receive_json()
    assert attachment_state(transport, offer)[0] == 'PREPARED'
    transport.client.cookies.set(COOKIE, transport.token)
    with stream(transport, offer, Origin=ORIGIN) as ws:
        attach(ws, transport.scope)
        ws.send_json({'kind': 'page', 'request_id': 1, 'method': 'turn/start', 'params': {'threadId': THREAD}})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert attachment_state(transport, offer) == ('DETACHED', None, None)


def test_wrong_challenge_logout_and_idle_retire_only_the_channel(transport, monkeypatch):
    offer = prepare(transport).json()
    with stream(transport, offer) as ws:
        hello(ws, transport.scope)
        assert ws.receive_json()['kind'] == 'challenge'
        ws.send_json({'kind': 'prove', 'challenge': 'incorrect'})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert attachment_state(transport, offer) == ('DETACHED', None, None)
    offer = prepare(transport, 'fresh-intent').json()
    monkeypatch.setattr(dashboard_session_presentations, '_RENEW_SECONDS', .1)
    with stream(transport, offer) as ws:
        attach(ws, transport.scope)
        transport.auth.logout(transport.token)
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert attachment_state(transport, offer) == ('DETACHED', None, None)


def test_disabled_and_unqualified_intents_are_refused(transport):
    assert prepare(transport, access='write', expected_writer_epoch=0).status_code == 409
    assert prepare(transport, intent='resume_saved').status_code == 409
    transport.app.state.local_codex_presentations = None
    assert prepare(transport).status_code == 409


@pytest.fixture
def pi_presentation(transport, monkeypatch):
    version, platform, architecture, fingerprint = _PI_PRESENTATION_BUILD
    build = NativeLaunchBuild(version, platform, architecture, 'sha256:' + 'a' * 64, fingerprint, 'qualified')
    mapping = ManagedNativeSession(transport.scope, 'open-pi', 'pi_rpc', 'native-pi', 'epoch', 'candidate',
                                   'inventory', 1, build, 'connection', 1, None, None)
    views = []
    state = SimpleNamespace(available=True, mapping=mapping, frames=views, refuse_open=False)

    def available(server_id, executor_id, session_id):
        return state.available and (server_id, executor_id, session_id) == tuple(asdict(transport.scope.session).values())

    @asynccontextmanager
    async def open_renderer(scope, *, columns, rows):
        assert scope == transport.scope
        if state.refuse_open:
            from nexus_connector_core import CoreError
            raise CoreError('NATIVE_UNAVAILABLE', 'pi_renderer')
        views.append(('open', columns, rows))

        async def frames():
            yield b'\x1b[2JExact Pi renderer bytes\n'
            await anyio.sleep_forever()

        try:
            yield frames()
        finally:
            views.append(('detach', columns, rows))

    async def prove(scope):
        assert scope == transport.scope
        return state.mapping, 'retained-owner'

    dispatch = SimpleNamespace(host=SimpleNamespace(pi_presentation_enabled=True, has_hosted_pi_renderer=available),
        prove_native_presentation_owner=prove, read_native_presentation_mapping=lambda *_: state.mapping,
        open_native_pi_renderer=open_renderer)
    transport.app.state.deps.connection_factory = transport.factory
    publish_local_pi_presentations(transport.app, dispatch)

    def enable_input():
        clock = SimpleNamespace(now_iso=lambda: '2026-01-01T00:00:00Z')
        authority = SimpleNamespace(clock=clock)

        def require_grant(_uow, *, scope, author, resolve_human, **_):
            assert scope == transport.scope and resolve_human(author.authority_ref)
            return 'fixture-grant', 1

        state.input_revision = 'pi-input-revision'
        transport.app.state.session_input_dispatch_options = {
            'session_input_capability_revision': lambda *_: state.input_revision,
        }
        monkeypatch.setattr(local_pi_presentations, 'build_execution_access', lambda _: authority)
        monkeypatch.setattr(session_interaction_authority, 'require_session_input_authority', require_grant)
        publish_local_pi_presentations(transport.app, dispatch)
        return transport.app.state.local_pi_presentations

    state.enable_input = enable_input
    return state


def _pi_review(transport, **options):
    return transport.client.post(PREFIX + f'/sessions/{transport.scope.session.session_id}/attachments:review',
        headers={'x-nexus-ui': '1'}, json={**document(transport.scope), 'presentation': 'pi', **options})


def _pi_prepare(transport, *, client_intent_id='pi-view', **options):
    review = _pi_review(transport)
    assert review.status_code == 200 and review.json()['attach_strategy'] == 'pi_local_read'
    return prepare(transport, client_intent_id, presentation='pi', capability_revision=review.json()['capability_revision'], **options)


def _prove_pi_ticket(ws, scope, *, columns=100, rows=36, editor=False):
    ws.send_json({'kind': 'hello', 'version': 1, **document(scope), 'columns': columns, 'rows': rows, 'editor': editor})
    challenge = ws.receive_json()
    assert challenge['kind'] == 'challenge'
    ws.send_json({'kind': 'prove', 'challenge': challenge['challenge']})
    return challenge['channel_id']


def test_pi_ticket_is_read_only_one_use_and_scoped_to_its_protocol(transport, pi_presentation):
    offer = _pi_prepare(transport).json()
    assert offer['live_updates'] is True
    with stream(transport, offer) as ws, pytest.raises(WebSocketDisconnect):
        hello(ws, transport.scope)
        ws.receive_json()
    assert attachment_state(transport, offer)[0] == 'PREPARED'
    with stream(transport, offer, protocol=PI_PRESENTATION_SUBPROTOCOL) as ws:
        _prove_pi_ticket(ws, transport.scope)
        assert ws.receive_json() == {'kind': 'attached', 'attachment_id': offer['attachment_id'], 'access': 'read'}
        assert ws.receive_bytes() == b'\x1b[2JExact Pi renderer bytes\n'
        ws.send_bytes(b'never sent to Pi')
        with pytest.raises(WebSocketDisconnect):
            ws.receive_bytes()
    assert attachment_state(transport, offer) == ('DETACHED', None, None)
    assert pi_presentation.frames == [('open', 100, 36), ('detach', 100, 36)]
    assert _pi_prepare(transport).json()['ticket'] is None
    with stream(transport, offer, protocol=PI_PRESENTATION_SUBPROTOCOL) as ws, pytest.raises(WebSocketDisconnect):
        _prove_pi_ticket(ws, transport.scope)


def test_pi_backpressure_releases_attachment_before_bounded_close(transport, pi_presentation, monkeypatch):
    offer = _pi_prepare(transport, client_intent_id='slow-pi-view').json()
    close_started, close_finished = threading.Event(), threading.Event()
    websocket = dashboard_session_presentations.WebSocket
    send_bytes, close = websocket.send_bytes, websocket.close

    def is_slow(ws):
        return ws.path_params.get('attachment_id') == offer['attachment_id']

    async def stalled_send(ws, payload):
        if is_slow(ws):
            await anyio.sleep_forever()
        await send_bytes(ws, payload)

    async def stalled_close(ws, code=1000, reason=None):
        if is_slow(ws):
            close_started.set()
            try:
                await anyio.sleep_forever()
            finally:
                close_finished.set()
        await close(ws, code=code, reason=reason)

    monkeypatch.setattr(websocket, 'send_bytes', stalled_send)
    monkeypatch.setattr(websocket, 'close', stalled_close)
    monkeypatch.setattr(dashboard_session_presentations, '_SEND_SECONDS', .2, raising=False)
    monkeypatch.setattr(dashboard_session_presentations, '_CLOSE_SECONDS', .8, raising=False)
    with stream(transport, offer, protocol=PI_PRESENTATION_SUBPROTOCOL) as slow:
        _prove_pi_ticket(slow, transport.scope)
        assert slow.receive_json()['kind'] == 'attached'
        assert close_started.wait(8)
        assert attachment_state(transport, offer) == ('DETACHED', None, None)
        assert pi_presentation.frames == [('open', 100, 36), ('detach', 100, 36)]
        fresh = _pi_prepare(transport, client_intent_id='reattach-pi-view').json()
        with stream(transport, fresh, protocol=PI_PRESENTATION_SUBPROTOCOL) as reader:
            _prove_pi_ticket(reader, transport.scope)
            assert reader.receive_json()['kind'] == 'attached'
            assert reader.receive_bytes() == b'\x1b[2JExact Pi renderer bytes\n'
            assert close_finished.wait(3)


@pytest.mark.parametrize('withdraw', ['logout', 'capability', 'attach_failure'])
def test_pi_renderer_retires_on_authority_loss_and_attach_failure(transport, pi_presentation, withdraw):
    offer = _pi_prepare(transport).json()
    if withdraw == 'attach_failure':
        pi_presentation.refuse_open = True
    with stream(transport, offer, protocol=PI_PRESENTATION_SUBPROTOCOL) as ws:
        _prove_pi_ticket(ws, transport.scope)
        if withdraw != 'attach_failure':
            assert ws.receive_json()['kind'] == 'attached'
            assert ws.receive_bytes()
            if withdraw == 'logout':
                transport.auth.logout(transport.token)
            else:
                pi_presentation.available = False
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert attachment_state(transport, offer) == ('DETACHED', None, None)
    assert pi_presentation.frames == ([] if withdraw == 'attach_failure' else [('open', 100, 36), ('detach', 100, 36)])


def test_pi_review_refuses_other_builds_writers_and_historical_runtime(transport, pi_presentation):
    assert _pi_prepare(transport, access='write', expected_writer_epoch=0).status_code == 409
    assert _pi_prepare(transport, intent='resume_saved').status_code == 409
    original = pi_presentation.mapping
    pi_presentation.mapping = replace(original, launch_build=replace(original.launch_build, build_identity='different'))
    assert _pi_review(transport).status_code == 409
    pi_presentation.mapping = original
    pi_presentation.available = False
    assert _pi_review(transport).status_code == 409


def test_pi_writer_replaces_the_exact_writer_and_replays_only_one_queued_input(transport, pi_presentation):
    service = pi_presentation.enable_input()
    scope = transport.scope
    reference = transport.auth.authority_reference(transport.token)
    web = session_interaction_authority.enqueue_human_input(factory=transport.factory, access=service.execution_access,
        authority_fence=transport.auth.authority_fence, current_capability_revision=service.next_turn_revision,
        scope=scope, author=InputAuthor(reference, 'web'), client_intent_id='web-before-pi',
        capability_revision=pi_presentation.input_revision, text='From the dashboard')

    def review_writer():
        response = _pi_review(transport, access='write')
        assert response.status_code == 200, response.text
        review = response.json()
        assert review['attach_strategy'] == 'pi_local_write'
        return review

    def writer_offer(intent, review, *, takeover=False):
        return prepare(transport, intent, presentation='pi', access='write', expected_writer_epoch=review['writer_epoch'],
                       capability_revision=review['capability_revision'], takeover=takeover)

    initial = review_writer()
    assert initial['writer_occupied'] is False and initial['writer_epoch'] == 0
    offer = writer_offer('pi-writer', initial).json()
    payload = {'kind': 'enqueue', 'request_id': 1, 'client_intent_id': 'native-pi-input',
               'capability_revision': initial['input_capability_revision'], 'content': {'type': 'text', 'text': 'From Pi'}}
    reader = _pi_prepare(transport, client_intent_id='pi-reader').json()
    with stream(transport, reader, protocol=PI_PRESENTATION_SUBPROTOCOL) as ws:
        _prove_pi_ticket(ws, scope)
        assert ws.receive_json()['access'] == 'read'
        assert ws.receive_bytes()
        ws.send_json(payload)
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

    with stream(transport, offer, protocol=PI_PRESENTATION_SUBPROTOCOL) as original:
        _prove_pi_ticket(original, scope)
        assert original.receive_json()['access'] == 'write'
        assert original.receive_bytes()
        original.send_json(payload)
        receipt = original.receive_json()
        assert receipt['status'] == 'QUEUED' and receipt['enqueue_sequence'] == web.sequence + 1
        assert receipt['operation_id'] is None and receipt['possible_effect'] is False
        current = review_writer()
        assert current['writer_occupied'] is True and current['writer_epoch'] == 1
        assert writer_offer('pi-no-takeover', current).status_code == 409
        replacement = writer_offer('pi-next-writer', current, takeover=True).json()
        observation = _pi_prepare(transport, client_intent_id='pi-observe-transfer').json()
        with stream(transport, observation, protocol=PI_PRESENTATION_SUBPROTOCOL) as observer:
            _prove_pi_ticket(observer, scope)
            assert observer.receive_json()['access'] == 'read'
            assert observer.receive_bytes()
            with stream(transport, replacement, protocol=PI_PRESENTATION_SUBPROTOCOL) as successor:
                _prove_pi_ticket(successor, scope)
                assert successor.receive_json()['access'] == 'write'
                assert successor.receive_bytes()
                with pytest.raises(WebSocketDisconnect):
                    original.receive_json()
                assert attachment_state(transport, observation)[0] == 'ACTIVE'
                successor.send_json(payload | {'request_id': 2})
                assert successor.receive_json() == receipt | {'request_id': 2}
                successor.send_json(payload | {'request_id': 3, 'scope': document(transport.sibling)['scope']})
                with pytest.raises(WebSocketDisconnect):
                    successor.receive_json()

    assert attachment_state(transport, offer)[0] == 'REPLACED'
    assert attachment_state(transport, replacement)[0] == 'DETACHED'
    with transport.factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM session_interaction_inputs').fetchone()[0] == 2


@pytest.mark.parametrize('write', [False, True])
def test_pi_client_reads_binary_frames_over_loopback_and_detaches(transport, pi_presentation, write):
    if write:
        pi_presentation.enable_input()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        host, port = listener.getsockname()
        server = uvicorn.Server(uvicorn.Config(transport.app, loop='asyncio', ws='wsproto',
            lifespan='off', log_level='warning', access_log=False, proxy_headers=False))
        thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(.02)
            assert server.started
            api = RemoteOperatorHTTP(f'http://{host}:{port}', token=transport.token,
                                     server_id=transport.scope.session.server_id)
            scope = document(transport.scope)
            reviewed = review_local_presentation(api, **scope, presentation='pi', write=write)
            revision = reviewed.capability_revision if write else reviewed
            with open_local_presentation(api, **scope, capability_revision=revision,
                                         client_intent_id='loopback-pi', pi_viewport=(80, 24),
                                         writer=reviewed if write else None) as reader:
                output = []
                if write:
                    receipt = reader.send_pi_input(intent='pi-loopback-input', text='Queue a message', output=output.append)
                    assert receipt['status'] == 'QUEUED' and receipt['possible_effect'] is False
                if not output:
                    output.append(reader.read_pi_output())
                assert output == [b'\x1b[2JExact Pi renderer bytes\n']
                offer = {'attachment_id': reader.attachment_id}
                assert attachment_state(transport, offer)[0] == 'ACTIVE'
        finally:
            server.should_exit = True
            thread.join(10)
            assert not thread.is_alive()
    assert attachment_state(transport, offer) == ('DETACHED', None, None)
    assert pi_presentation.frames == [('open', 80, 24), ('detach', 80, 24)]


@pytest.mark.parametrize('editor', [False, True])
def test_pi_input_with_lost_reply_requires_recovery_of_the_same_intent(monkeypatch, editor):
    link = _LocalPresenter(None, None, 'viewer', live_updates=True, input_revision='revision')
    calls = []

    def lost_reply(frame, **_):
        calls.append(frame)
        raise OSError('Reply lost')

    monkeypatch.setattr(link, 'exchange', lost_reply)
    with pytest.raises(ConnectionError) as raised:
        if editor:
            link.edit_pi_input(intent='original-intent', key='enter', text=None, output=lambda _: None)
        else:
            link.send_pi_input(intent='original-intent', text='Queued once', output=lambda _: None)
    assert raised.value.code == 'OUTCOME_UNKNOWN' and raised.value.possible_effect
    assert [request['client_intent_id'] for request in calls] == ['original-intent']


@pytest.mark.parametrize('action', ['steer', 'interrupt'])
def test_pi_control_separates_review_and_uncertain_confirmation(monkeypatch, action):
    link = _LocalPresenter(None, None, 'viewer', live_updates=True, input_revision='revision')
    calls = []
    intent = f'pi_{action}_' + '1' * 32
    review_id = 'r' * 32

    def exchange(frame, **_):
        calls.append(frame)
        if frame['kind'] == f'{action}_review':
            return {'kind': f'{action}_review', 'request_id': frame['request_id'],
                    f'{action}_review': {'status': 'reviewed', 'review_id': review_id}}
        raise OSError('Reply lost')

    monkeypatch.setattr(link, 'exchange', exchange)
    assert link.review_pi_control(action=action, intent=intent, output=lambda _: None) == review_id
    with pytest.raises(ConnectionError) as lost:
        link.decide_pi_control(action=action, review_id=review_id, confirm=True, output=lambda _: None)
    assert lost.value.code == 'OUTCOME_UNKNOWN' and lost.value.possible_effect
    assert calls == [
        {'kind': f'{action}_review', 'request_id': 1, 'client_intent_id': intent, 'capability_revision': 'revision'},
        {'kind': f'{action}_confirm', 'request_id': 2, 'review_id': review_id},
    ]


def test_pi_interrupt_review_cannot_change_action_or_survive_writer_replacement(transport, pi_presentation, monkeypatch):
    services = pi_presentation.enable_input()

    @asynccontextmanager
    async def editor(scope, **_):
        assert scope == transport.scope
        first = True

        async def output():
            nonlocal first
            if first:
                first = False
                return b'Pi transcript'
            await anyio.sleep_forever()

        async def edit(*_args, **_kwargs):
            pytest.fail('An interrupt must leave the Pi draft alone')

        yield edit, output

    transport.app.state.local_pi_presentations = replace(services, open_editor=editor)
    target = InterruptTargetView(target=ObservedRunTarget(kind='observed_run', run_ref='prun_' + '1' * 32),
                                 capability_revision='exact-run', queue_revision=0)
    monkeypatch.setattr(dashboard_session_presentations, 'review_exact_interrupt', lambda *_: target)
    monkeypatch.setattr(dashboard_session_presentations, 'request_exact_human_interrupt',
                        lambda **_: pytest.fail('An invalid review reached interrupt admission'))
    monkeypatch.setattr(dashboard_session_presentations, 'steer_human_input',
                        lambda **_: pytest.fail('An interrupt review became a steer intent'))

    def offer(intent, *, takeover=False):
        reply = _pi_review(transport, access='write').json()
        result = prepare(transport, intent, presentation='pi', access='write',
            expected_writer_epoch=reply['writer_epoch'], capability_revision=reply['capability_revision'],
            takeover=takeover)
        assert result.status_code == 201, result.text
        return result.json()

    def review(ws, request_id):
        ws.send_json({'kind': 'interrupt_review', 'request_id': request_id,
                      'capability_revision': pi_presentation.input_revision, 'client_intent_id': 'interrupt-intent'})
        result = ws.receive_json()
        assert result['interrupt_review']['status'] == 'reviewed'
        return result['interrupt_review']['review_id']

    first = offer('native-pi-first-writer')
    with stream(transport, first, protocol=PI_PRESENTATION_SUBPROTOCOL) as old:
        _prove_pi_ticket(old, transport.scope, editor=True)
        assert old.receive_json()['access'] == 'write'
        assert old.receive_bytes() == b'Pi transcript'
        review_id = review(old, 1)
        old.send_json({'kind': 'steer_confirm', 'request_id': 2, 'review_id': review_id})
        assert old.receive_json()['steer_confirm'] == {'status': 'refused'}
        old.send_json({'kind': 'interrupt_confirm', 'request_id': 3, 'review_id': review_id})
        assert old.receive_json()['interrupt_confirm'] == {'status': 'refused'}
        last_review = review(old, 4)
        second = offer('native-pi-next-writer', takeover=True)
        with stream(transport, second, protocol=PI_PRESENTATION_SUBPROTOCOL) as current:
            _prove_pi_ticket(current, transport.scope, editor=True)
            assert current.receive_json()['access'] == 'write'
            assert current.receive_bytes() == b'Pi transcript'
            old.send_json({'kind': 'interrupt_confirm', 'request_id': 5, 'review_id': last_review})
            with pytest.raises(WebSocketDisconnect):
                old.receive_json()
            current.send_json({'kind': 'interrupt_confirm', 'request_id': 1, 'review_id': last_review})
            assert current.receive_json()['interrupt_confirm'] == {'status': 'refused'}
    assert attachment_state(transport, first)[0] == 'REPLACED'


def test_writer_and_web_share_queue_with_exact_scope_and_idempotency(transport, monkeypatch):
    app, factory, scope = transport.app, transport.factory, transport.scope
    service = app.state.local_codex_presentations
    clock = SimpleNamespace(now_iso=lambda: '2026-01-01T00:00:00Z')
    service = replace(service, execution_access=SimpleNamespace(clock=clock),
                      next_turn_revision=lambda *_: 'input-revision')
    app.state.local_codex_presentations = service
    grants = []

    def grant(_uow, *, scope, author, resolve_human, **_):
        assert scope == transport.scope and resolve_human(author.authority_ref)
        grants.append(author.surface)
        return 'fixture-grant', 1

    monkeypatch.setattr(session_interaction_authority, 'require_session_input_authority', grant)
    reference = transport.auth.authority_reference(transport.token)
    web = session_interaction_authority.enqueue_human_input(factory=factory, access=service.execution_access,
        authority_fence=transport.auth.authority_fence, current_capability_revision=service.next_turn_revision,
        scope=scope, author=InputAuthor(reference, 'web'), client_intent_id='web-intent',
        capability_revision='input-revision', text='From Home')
    path = PREFIX + f'/sessions/{scope.session.session_id}/attachments:review'

    def writer_review():
        return transport.client.post(path, headers={'x-nexus-ui': '1'},
                                     json={**document(scope), 'access': 'write'}).json()

    initial = writer_review()
    assert initial['attach_strategy'] == 'codex_local_write' and initial['writer_occupied'] is False
    assert initial['writer_epoch'] == 0 and initial['input_capability_revision'] == 'input-revision'
    offer = prepare(transport, 'writer-one', access='write', expected_writer_epoch=initial['writer_epoch']).json()
    payload = {'kind': 'enqueue', 'request_id': 1, 'thread_id': THREAD, 'client_intent_id': 'native-intent',
               'capability_revision': 'input-revision', 'content': {'type': 'text', 'text': 'From Codex'}}
    reader = prepare(transport, 'reader').json()
    with stream(transport, reader) as ws, pytest.raises(WebSocketDisconnect):
        attach(ws, scope)
        ws.send_json(payload)
        ws.receive_json()

    with stream(transport, offer) as original:
        attach(original, scope)
        original.send_json(payload)
        receipt = original.receive_json()
        assert receipt == {'kind': 'enqueue', 'request_id': 1, 'input_id': receipt['input_id'],
                           'enqueue_sequence': web.sequence + 1, 'status': 'QUEUED',
                           'operation_id': None, 'possible_effect': False}
        current = writer_review()
        assert current['writer_epoch'] == 1 and current['writer_occupied'] is True
        assert prepare(transport, 'no-takeover', access='write', expected_writer_epoch=1).status_code == 409
        replacement = prepare(transport, 'writer-two', access='write', expected_writer_epoch=1, takeover=True).json()
        with stream(transport, replacement) as next_writer:
            attach(next_writer, scope)
            original.send_json(payload)
            with pytest.raises(WebSocketDisconnect):
                original.receive_json()
            next_writer.send_json(payload | {'request_id': 2})
            assert next_writer.receive_json() == receipt | {'request_id': 2}
            next_writer.send_json(payload | {'request_id': 3, 'thread_id': 'sibling-thread'})
            with pytest.raises(WebSocketDisconnect):
                next_writer.receive_json()

    with factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute('''SELECT surface,content,source_grant_id,source_grant_revision
            FROM session_interaction_inputs ORDER BY enqueue_sequence''').fetchall()
        assert [tuple(row) for row in rows] == [('web', 'From Home', 'fixture-grant', 1),
                                               ('native_terminal', 'From Codex', 'fixture-grant', 1)]
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
    assert grants == ['web', 'native_terminal']


def test_review_confirmation_admits_only_the_control_that_was_reviewed(transport, monkeypatch):
    app = transport.app
    app.state.local_codex_presentations = replace(app.state.local_codex_presentations,
        next_turn_revision=lambda *_: 'input-revision')
    app.state.session_input_dispatch_options = {
        'session_input_capability_revision': lambda *_: 'input-revision',
        'session_steer_revisions': lambda *_: ('capability', 'effect'),
    }
    app.state.inventory_fresh_publications = None
    target = NativeTurnTarget(kind='native_turn', turn_id=THREAD)
    exact = {'target': target, 'capability_revision': 'capability', 'queue_revision': 0}
    monkeypatch.setattr(dashboard_session_presentations, 'review_exact_interrupt',
                        lambda *_: InterruptTargetView(**exact))
    monkeypatch.setattr(dashboard_session_presentations, 'review_exact_steer',
                        lambda *_: SteerTargetView(**exact, effect='same_turn', effect_revision='effect'))
    effects = []

    def steer(**review):
        effects.append(('steer', review['native_turn_id'], review['text']))
        return SimpleNamespace(input_id='fixture-input')

    def interrupt(**review):
        effects.append(('interrupt', review['native_turn_id']))

    monkeypatch.setattr(dashboard_session_presentations, 'steer_human_input', steer)
    monkeypatch.setattr(dashboard_session_presentations, 'request_exact_human_interrupt', interrupt)
    offer = prepare(transport, 'reviewer', access='write', expected_writer_epoch=0).json()
    with stream(transport, offer) as ws:
        attach(ws, transport.scope)

        def exchange(kind, request_id, **payload):
            ws.send_json({'kind': kind, 'request_id': request_id, **payload})
            return ws.receive_json()[kind]

        scope = {'thread_id': THREAD, 'turn_id': THREAD, 'client_intent_id': 'native-control'}
        message = {'content': {'type': 'text', 'text': 'Use a different file'}}
        review = exchange('steer_review', 1, **scope, **message)
        assert exchange('interrupt_confirm', 2, review_id=review['review_id']) == {'status': 'refused'}
        assert exchange('steer_confirm', 3, review_id=review['review_id']) == {'status': 'refused'}
        assert not effects
        review = exchange('steer_review', 4, **scope, **message)
        assert exchange('steer_confirm', 5, review_id=review['review_id']) == {
            'status': 'recorded', 'input_id': 'fixture-input'}
        review = exchange('interrupt_review', 6, **scope)
        assert exchange('interrupt_confirm', 7, review_id=review['review_id']) == {'status': 'recorded'}
        assert exchange('interrupt_confirm', 8, review_id=review['review_id']) == {'status': 'refused'}
    assert effects == [('steer', THREAD, 'Use a different file'), ('interrupt', THREAD)]


@pytest.mark.parametrize('change', ['different-thread', 'owner-replaced', 'operator-logout'])
def test_context_requires_matching_thread_and_authority_throughout_read(transport, tmp_path, change):
    service = transport.app.state.local_codex_presentations
    current_owner = 'same-owner'

    async def prove(scope):
        mapping, _ = await service.prove_owner(scope)
        return mapping, current_owner

    async def context(scope):
        nonlocal current_owner
        assert scope == transport.scope
        if change == 'operator-logout':
            transport.auth.logout(transport.token)
        if change == 'owner-replaced':
            current_owner = 'replacement'
        context = viewer_context(tmp_path)
        return context.model_copy(update={'thread_id': 'sibling'}) if change == 'different-thread' else context

    transport.app.state.local_codex_presentations = replace(service, prove_owner=prove, read_context=context)
    offer = prepare(transport).json()
    with stream(transport, offer) as ws:
        attach(ws, transport.scope)
        ws.send_json({'kind': 'context', 'request_id': 1})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert attachment_state(transport, offer) == ('DETACHED', None, None)


def test_explicit_detach_requires_the_same_channel(transport):
    offer = prepare(transport).json()
    path = PREFIX + '/attachments/' + offer['attachment_id'] + '/detach'
    with stream(transport, offer) as ws:
        channel_id = attach(ws, transport.scope)
        body = document(transport.scope)
        refused = transport.client.post(path, headers={'x-nexus-ui': '1'},
            json={**body, 'channel_id': 'another-channel'})
        assert refused.status_code == 404
        result = transport.client.post(path, headers={'x-nexus-ui': '1'}, json={**body, 'channel_id': channel_id})
        assert result.status_code == 200
        ws.send_json({'kind': 'page', 'request_id': 1, 'method': 'thread/items/list', 'params': {'threadId': THREAD}})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert attachment_state(transport, offer) == ('DETACHED', None, None)


@pytest.mark.parametrize('quit_mode', ['eof', 'logout', 'follow'])
def test_loopback_network_carries_context_and_history_then_detaches(transport, quit_mode, tmp_path, monkeypatch):
    if quit_mode == 'logout':
        monkeypatch.setattr(dashboard_session_presentations, '_RENEW_SECONDS', 1)
    positions = []
    terminal_status = []
    notice = {'method': 'turn/started', 'params': {'threadId': THREAD, 'turn': {
        'id': 'turn', 'items': [], 'status': 'inProgress', 'itemsView': 'notLoaded', 'error': None}}}
    with transport.factory.unit_of_work() as uow:
        original_input = enqueue(uow, transport.scope, text='Queued in the selected session')
        sibling_input = enqueue(uow, transport.sibling, text='Queued in the sibling session')
    if quit_mode == 'follow':
        transport.app.state.local_codex_presentations = replace(
            transport.app.state.local_codex_presentations, live_updates=True)

        def updates(*_args, after_sequence, active_turn, **_kwargs):
            positions.append((after_sequence, active_turn))
            if after_sequence == 0:
                return 1, 'turn', {'notifications': [notice], 'has_more': False}
            return 1, 'turn', {'notifications': [], 'has_more': False}

        monkeypatch.setattr(codex_presenter_channel, 'read_codex_history_updates', updates)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        host, port = listener.getsockname()
        server = uvicorn.Server(uvicorn.Config(transport.app, loop='asyncio', ws='wsproto',
            lifespan='off', log_level='warning', access_log=False, proxy_headers=False))
        thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(.02)
            assert server.started
            api = RemoteOperatorHTTP(f'http://{host}:{port}', token=transport.token,
                                     server_id=transport.scope.session.server_id)
            revision = review_local_presentation(api, **document(transport.scope))
            assert revision == 'capability-1'
            with transport.factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM session_attachments').fetchone()[0] == 0
            with open_local_presentation(api, **document(transport.scope),
                                         capability_revision=revision, client_intent_id='loopback') as peer:
                with transport.factory.unit_of_work(write=False) as uow:
                    offer = dict(uow.connection.execute(
                        'SELECT attachment_id FROM session_attachments WHERE client_intent_id=?', ('loopback',)
                    ).fetchone())
                assert attachment_state(transport, offer)[0] == 'ACTIVE'
                assert offer['attachment_id'] == peer.attachment_id
                with local_codex_relay(peer, viewer_home=str(tmp_path), platform_os='windows',
                                       report_input_status=terminal_status.append) as endpoint:
                    port = urlsplit(endpoint.address).port
                    with socket.create_connection(('127.0.0.1', port), timeout=4) as foreign:
                        denied = open_viewer(endpoint, foreign, token=endpoint.token,
                                             extra=[(b'origin', b'http://foreign.test')])
                        assert isinstance(next(next_event(foreign, denied)), RejectConnection)
                    with socket.create_connection(('127.0.0.1', port), timeout=4) as viewer:
                        wire = open_viewer(endpoint, viewer, token=endpoint.token)
                        assert isinstance(next(next_event(viewer, wire)), AcceptConnection)
                        assert rpc(viewer, wire, 1, 'initialize')['result']['platformOs'] == 'windows'
                        response = rpc(viewer, wire, 2, 'thread/resume', threadId=THREAD)
                        assert response['result']['thread']['id'] == THREAD
                        assert response['result']['cwd'] == str(tmp_path)
                        for method in ['thread/turns/list', 'thread/items/list']:
                            assert rpc(viewer, wire, method, method, threadId=THREAD)['result']['data'] == []
                        assert rpc(viewer, wire, 3, 'thread/items/list', threadId='sibling')['error']['code'] == -32602
                        assert rpc(viewer, wire, 4, 'turn/start', threadId=THREAD)['error']['code'] == -32601
                        sibling_thread = '310872fd-606c-4467-91a0-c5d41a588712'
                        assert rpc(viewer, wire, 'resume-sibling', 'thread/resume',
                                   threadId=sibling_thread)['error']['code'] == -32602
                        assert rpc(viewer, wire, 'fork-current', 'thread/fork', threadId=THREAD)['error']['code'] == -32601
                        selected = rpc(viewer, wire, 'read-selected', 'thread/read', threadId=THREAD)
                        assert selected['result']['thread']['id'] == THREAD
                        if quit_mode == 'follow':
                            assert not positions
                            assert rpc(viewer, wire, 5, 'thread/read', threadId=THREAD,
                                       includeTurns=True)['result']['thread']['turns'] == []
                            changed = next(next_event(viewer, wire))
                            assert json.loads(changed.data) == {'jsonrpc': '2.0', **notice}
                            deadline = time.monotonic() + 4
                            while len(positions) < 2 and time.monotonic() < deadline:
                                time.sleep(.02)
                            assert positions[:2] == [(0, None), (1, 'turn')]
                        if quit_mode == 'logout':
                            transport.auth.logout(transport.token)
                            assert viewer.recv(1024) == b''
                            assert len(terminal_status) == 1 and 'lost its session presentation' in terminal_status[0]
                        else:
                            assert not terminal_status
                    deadline = time.monotonic() + 5
                    while attachment_state(transport, offer)[0] != 'DETACHED' and time.monotonic() < deadline:
                        time.sleep(.02)
                    assert attachment_state(transport, offer) == ('DETACHED', None, None)
        finally:
            server.should_exit = True
            thread.join(10)
            assert not thread.is_alive()
    with transport.factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute("""
            SELECT executor_id, session_id, owner_generation, input_id, status, operation_id
            FROM session_interaction_inputs ORDER BY executor_id
        """).fetchall()
        assert [tuple(row) for row in rows] == [
            (scope.session.executor_id, scope.session.session_id, scope.generation.value, receipt.input_id, 'QUEUED', None)
            for scope, receipt in ((transport.scope, original_input), (transport.sibling, sibling_input))
        ]
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0


def test_client_refuses_foreign_server_before_sending_the_operator_cookie(transport):
    arguments = {**document(transport.scope), 'capability_revision': 'capability-1', 'client_intent_id': 'foreign'}
    foreign = RemoteOperatorHTTP('https://example.test', token=transport.token,
                                 server_id=transport.scope.session.server_id)
    with pytest.raises(ConnectionError) as refused, open_local_presentation(foreign, **arguments):
        pytest.fail('A nonlocal presentation must not be prepared')
    assert refused.value.code == 'PRESENTATION_LOCAL_REQUIRED'
    sibling = RemoteOperatorHTTP(ORIGIN, token=transport.token, server_id='another-server')
    with pytest.raises(ConnectionError) as refused, open_local_presentation(sibling, **arguments):
        pytest.fail('A foreign Server scope must not be prepared')
    assert refused.value.code == 'PRESENTATION_UNAVAILABLE'


def test_native_inline_history_has_shared_scope_and_refuses_partial_reads(tmp_path):
    calls = []
    state = {'cursor': None}

    def page(*, method, params):
        assert params['threadId'] == THREAD
        calls.append(method)
        data = [{'id': 'turn', 'status': 'completed'}] if method == 'thread/turns/list' else [
            {'turnId': 'turn', 'item': {'type': 'agentMessage', 'id': 'item', 'text': 'fixture'}}]
        return {'data': data, 'nextCursor': state['cursor']}

    protocol = CodexViewerProtocol(context=viewer_context(tmp_path), read_page=page,
                                   viewer_home=str(tmp_path), platform_os='windows')
    protocol.handle({'id': 1, 'method': 'initialize'})
    read = {'id': 2, 'method': 'thread/read', 'params': {'threadId': THREAD, 'includeTurns': True}}
    assert protocol.handle(read)['result']['thread']['turns'] == [{
        'id': 'turn', 'status': 'completed', 'itemsView': 'summary',
        'items': [{'type': 'agentMessage', 'id': 'item', 'text': 'fixture'}]}]
    assert calls == ['thread/turns/list', 'thread/items/list']
    state['cursor'] = 'continuation'
    assert protocol.handle(read)['error']['code'] == -32601
    assert calls[-1] == 'thread/turns/list' and calls.count('thread/items/list') == 1


def test_native_next_turn_accepts_only_exact_plain_text_and_keeps_steer_separate(tmp_path):
    context = viewer_context(tmp_path)
    recorded = []

    def send(**kwargs):
        recorded.append(kwargs)
        return CodexPendingInput('receipt', 'Message recorded')

    protocol = CodexViewerProtocol(context=context, read_page=lambda **_: {'data': [], 'nextCursor': None},
        viewer_home=str(tmp_path), platform_os='windows', send_next_turn=send)
    protocol.handle({'id': 1, 'method': 'initialize'})
    protocol.handle({'id': 2, 'method': 'thread/read', 'params': {'threadId': THREAD, 'includeTurns': True}})
    client_id = '24447be9-beb8-47a4-ace2-a734561c7b88'
    params = {'threadId': THREAD, 'clientUserMessageId': client_id,
        'input': [{'type': 'text', 'text': 'My text.\nSecond line.', 'text_elements': []}],
        'turnTrigger': 'user', 'cwd': context.cwd, 'model': context.model,
        'approvalPolicy': context.approval_policy, 'serviceTier': 'default', 'effort': context.reasoning_effort}
    request = {'id': 3, 'method': 'turn/start', 'params': params}
    for changed in ({'threadId': 'sibling'}, {'cwd': '/other'}, {'model': 'other'}, {'sandboxPolicy': {}},
                    {'clientUserMessageId': 'different'}, {'input': [{'type': 'text', 'text': '/send something'}]},
                    {'input': [{'type': 'image', 'url': 'file:///unavailable'}]}, {'unexpected': True}):
        assert 'error' in protocol.handle(request | {'params': params | changed})
    steer = protocol.handle(request | {'method': 'turn/steer'})
    assert 'confirm reorientation' in steer['error']['message']
    assert not recorded
    assert protocol.handle(request) is None
    assert recorded == [{'thread_id': THREAD, 'intent': 'codex_' + client_id, 'text': 'My text.\nSecond line.'}]
    assert protocol.pending_delivery == (3, CodexPendingInput('receipt', 'Message recorded'))
    following = request | {'id': 5, 'params': params | {'clientUserMessageId': '766bc061-86e2-4df3-a032-faafb16b3987'}}
    assert 'preceding message' in protocol.handle(following)['error']['message']
    assert protocol.pending_delivery[0] == 3 and len(recorded) == 1


def test_native_steer_projects_only_the_exact_turn_and_text(tmp_path):
    calls = []
    target = 'cb17abba-cc2d-4d15-86fc-bc4d802f14ed'
    message_id = '24447be9-beb8-47a4-ace2-a734561c7b88'

    def steer(**kwargs):
        calls.append(kwargs)
        return CodexPendingInput('record', 'Reorientation recorded', steer_target=target)

    protocol = CodexViewerProtocol(context=viewer_context(tmp_path), viewer_home=str(tmp_path), platform_os='windows',
        read_page=lambda **_: {'data': [], 'nextCursor': None}, send_next_turn=lambda **_: pytest.fail('Unexpected send'),
        steer=steer)
    protocol.handle({'id': 1, 'method': 'initialize'})
    protocol.handle({'id': 2, 'method': 'thread/read', 'params': {'threadId': THREAD, 'includeTurns': True}})
    body = {'threadId': THREAD, 'expectedTurnId': target, 'clientUserMessageId': message_id,
            'input': [{'type': 'text', 'text': 'Use the other file', 'text_elements': []}]}
    request = {'id': 3, 'method': 'turn/steer', 'params': body}
    for change in ({'threadId': target}, {'expectedTurnId': 'latest'}, {'additionalContext': []}, {'input': []}):
        assert 'error' in protocol.handle(request | {'params': body | change})
    assert not calls
    assert protocol.handle(request) is None
    assert calls == [{'thread_id': THREAD, 'turn_id': target, 'intent': 'codex_steer_' + message_id,
                      'text': 'Use the other file'}]
    assert protocol.pending_delivery[1].steer_target == target
    protocol.pending_delivery = None
    assert 'reviewed for reorientation' in protocol.handle({'id': 4, 'method': 'turn/start',
        'params': {key: value for key, value in body.items() if key != 'expectedTurnId'}})['error']['message']


def test_native_interrupt_requires_an_exact_target_and_uses_a_separate_receipt(tmp_path):
    calls = []
    target = 'cb17abba-cc2d-4d15-86fc-bc4d802f14ed'

    def interrupt(**kwargs):
        calls.append(kwargs)
        return CodexPendingInterrupt(kwargs['intent'], 'Interruption recorded')

    protocol = CodexViewerProtocol(context=viewer_context(tmp_path), viewer_home=str(tmp_path), platform_os='windows',
        read_page=lambda **_: {'data': [], 'nextCursor': None},
        send_next_turn=lambda **_: pytest.fail('A control must not send a new turn'), interrupt=interrupt)
    body = {'threadId': THREAD, 'turnId': target}
    request = {'id': 3, 'method': 'turn/interrupt', 'params': body}
    protocol.handle({'id': 1, 'method': 'initialize'})
    assert 'error' in protocol.handle(request)
    protocol.handle({'id': 2, 'method': 'thread/read', 'params': {'threadId': THREAD, 'includeTurns': True}})
    for change in ({'threadId': target}, {'turnId': 'latest'}, {'text': 'stop'}):
        assert 'error' in protocol.handle(request | {'params': body | change})
    assert not calls
    preceding = (4, CodexPendingInput('pending', 'Reorientation recorded', steer_target=target))
    protocol.pending_delivery = preceding
    assert protocol.handle(request) is None
    assert protocol.pending_delivery == preceding
    assert len(calls) == 1
    assert calls[0] == {'thread_id': THREAD, 'turn_id': target, 'intent': protocol.pending_interrupt[1].intent}
    assert calls[0]['intent'].startswith('codex_interrupt_')
    assert 'awaiting confirmation' in protocol.handle(request | {'id': 5})['error']['message']
    assert len(calls) == 1
