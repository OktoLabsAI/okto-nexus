"""Exercise the local presentation protocol across HTTP and WebSocket."""

import json
import socket
import threading
import time
from dataclasses import asdict
from types import SimpleNamespace
from urllib.parse import urlsplit

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
from okto_nexus.adapters.outbound.local_presenter_client import open_local_presentation
from okto_nexus.adapters.outbound.operator_client import RemoteOperatorHTTP
from okto_nexus.application import codex_presenter_channel
from okto_nexus.application.codex_presenter_history import CodexHistorySnapshot
from okto_nexus.application.codex_viewer_protocol import (
    CodexViewerContext,
    CodexViewerProtocol,
)
from okto_nexus.application.session_attachment_broker import SessionAttachmentBroker
from okto_nexus.application.terminal_connection import ConnectionError
from tests.session_interaction.test_queue_storage import database as queue_database

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
    app.state.deps = SimpleNamespace(config=SimpleNamespace(transport_security='http_https'))
    app.state.operator_auth = auth
    broker = SessionAttachmentBroker(factory, authority_fence=auth.authority_fence,
        current_capability=lambda *_: 'capability-1')

    async def prove(requested):
        assert requested == scope
        return SimpleNamespace(codex_thread_id=THREAD), 'same-owner'

    monkeypatch.setattr(codex_presenter_channel, 'read_codex_history_snapshot',
                        lambda *_args, **_kwargs: CodexHistorySnapshot(0, 0, (), ()))
    app.state.local_codex_presentations = dashboard_session_presentations.LocalCodexPresentations(
        broker, prove, object())
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


def stream(transport, offer, *, path='', **headers):
    return transport.client.websocket_connect('ws://127.0.0.1' + PREFIX + '/attachments/'
        + offer['attachment_id'] + '/stream' + path,
        headers={'Authorization': 'Bearer ' + offer['ticket'], **headers}, subprotocols=[SUBPROTOCOL])


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
    assert prepare(transport, access='write').status_code == 409
    assert prepare(transport, intent='resume_saved').status_code == 409
    transport.app.state.local_codex_presentations = None
    assert prepare(transport).status_code == 409


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


@pytest.mark.parametrize('quit_mode', ['eof', 'logout'])
def test_loopback_network_carries_history_and_releases_on_eof(transport, quit_mode, tmp_path, monkeypatch):
    if quit_mode == 'logout':
        monkeypatch.setattr(dashboard_session_presentations, '_RENEW_SECONDS', 1)
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
            with open_local_presentation(api, **document(transport.scope),
                                         capability_revision='capability-1', client_intent_id='loopback') as peer:
                with transport.factory.unit_of_work(write=False) as uow:
                    offer = dict(uow.connection.execute(
                        'SELECT attachment_id FROM session_attachments WHERE client_intent_id=?', ('loopback',)
                    ).fetchone())
                assert attachment_state(transport, offer)[0] == 'ACTIVE'
                with local_codex_relay(peer, context=viewer_context(tmp_path), viewer_home=str(tmp_path),
                                       platform_os='windows') as endpoint:
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
                        for method in ['thread/turns/list', 'thread/items/list']:
                            assert rpc(viewer, wire, method, method, threadId=THREAD)['result']['data'] == []
                        assert rpc(viewer, wire, 3, 'thread/items/list', threadId='sibling')['error']['code'] == -32602
                        assert rpc(viewer, wire, 4, 'turn/start', threadId=THREAD)['error']['code'] == -32601
                        if quit_mode == 'logout':
                            transport.auth.logout(transport.token)
                            assert viewer.recv(1024) == b''
                    deadline = time.monotonic() + 5
                    while attachment_state(transport, offer)[0] != 'DETACHED' and time.monotonic() < deadline:
                        time.sleep(.02)
                    assert attachment_state(transport, offer) == ('DETACHED', None, None)
        finally:
            server.should_exit = True
            thread.join(10)
            assert not thread.is_alive()


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
