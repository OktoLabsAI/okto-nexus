"""Exercise the local presentation protocol across HTTP and WebSocket."""

import json
import socket
import threading
import time
from dataclasses import asdict
from types import SimpleNamespace

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from wsproto import ConnectionType, WSConnection
from wsproto.events import AcceptConnection, CloseConnection, Request, TextMessage

from okto_nexus.adapters.inbound.http import dashboard_session_presentations
from okto_nexus.adapters.inbound.http.operator_auth import COOKIE, OperatorAuth
from okto_nexus.adapters.outbound.operator_client import RemoteOperatorHTTP
from okto_nexus.application import codex_presenter_channel
from okto_nexus.application.codex_presenter_history import CodexHistorySnapshot
from okto_nexus.application.session_attachment_broker import SessionAttachmentBroker
from tests.session_interaction.test_queue_storage import database as queue_database

database = queue_database
THREAD = 'bdfe5b81-54cf-43cf-8001-5de670d3dd69'
PREFIX = '/api/v1/runtime-management'
SUBPROTOCOL = 'nexus.presenter.v1'
ORIGIN = 'http://127.0.0.1'


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


def test_loopback_network_carries_history_and_releases_on_eof(transport):
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
            api = RemoteOperatorHTTP(f'http://{host}:{port}', token=transport.token)
            offer = api('POST', PREFIX + f'/sessions/{transport.scope.session.session_id}/attachments:prepare',
                {**document(transport.scope), 'capability_revision': 'capability-1', 'client_intent_id': 'loopback',
                 'intent': 'attach_live', 'access': 'read'})
            with socket.create_connection((host, port), timeout=5) as peer:
                wire = WSConnection(ConnectionType.CLIENT)
                peer.sendall(wire.send(Request(host=f'{host}:{port}',
                    target=PREFIX + '/attachments/' + offer['attachment_id'] + '/stream',
                    subprotocols=[SUBPROTOCOL], extra_headers=[
                        (b'authorization', ('Bearer ' + offer['ticket']).encode()),
                        (b'cookie', f'{COOKIE}={transport.token}'.encode()),
                    ])))

                def events():
                    data = peer.recv(64 * 1024)
                    assert data
                    wire.receive_data(data)
                    return list(wire.events())

                def exchange(value):
                    peer.sendall(wire.send(TextMessage(data=json.dumps(value))))
                    response = ''
                    while True:
                        for event in events():
                            assert not isinstance(event, CloseConnection)
                            if isinstance(event, TextMessage):
                                response += event.data
                                if event.message_finished:
                                    return json.loads(response)

                candidates = events()
                while not candidates:
                    candidates = events()
                assert len(candidates) == 1 and isinstance(candidates[0], AcceptConnection)
                assert candidates[0].subprotocol == SUBPROTOCOL
                challenge = exchange({'kind': 'hello', 'version': 1, **document(transport.scope)})
                assert exchange({'kind': 'prove', 'challenge': challenge['challenge']})['kind'] == 'attached'
                response = exchange({'kind': 'page', 'request_id': 1,
                    'method': 'thread/turns/list', 'params': {'threadId': THREAD}})
                assert response['kind'] == 'page' and response['page']['data'] == []
            deadline = time.monotonic() + 5
            while attachment_state(transport, offer)[0] != 'DETACHED' and time.monotonic() < deadline:
                time.sleep(.02)
            assert attachment_state(transport, offer) == ('DETACHED', None, None)
        finally:
            server.should_exit = True
            thread.join(10)
            assert not thread.is_alive()
