"""Human operator cookies over real HTTP handlers, without local lifecycle fallback."""
from email.message import Message
from io import BytesIO, StringIO
import json
from types import SimpleNamespace
import time
from urllib.error import HTTPError, URLError

import pytest

import test_terminal_work as work_fixtures
from okto_nexus.adapters.outbound import operator_client
from okto_nexus.adapters.outbound.operator_client import OperatorProfile, RemoteOperatorHTTP, server_origin
from okto_nexus.application.terminal_connection import ConnectionError, RemoteTerminalConnection
from okto_nexus.application.terminal_connection import document_revision
from okto_nexus.application.terminal_work import TerminalWork

work = work_fixtures.work
connected_local = work_fixtures.connected_local
local_setup = work_fixtures.local_setup
qualified_contract = work_fixtures.qualified_contract
ORIGIN = 'https://nexus.example'
ACCOUNT = {'username': 'human', 'password': 'synthetic-human-password'}


class MemoryVault:
    def __init__(self):
        self.values = {}

    def set(self, service, name, value):
        self.values[service, name] = value

    def get(self, service, name):
        return self.values[service, name]

    def remove(self, service, name):
        del self.values[service, name]


class HTTPBridge:
    """Only the wire is adapted; authorization/receipts/dispatch remain real."""
    def __init__(self, client):
        self.client, self.calls, self.after = client, [], None

    def open(self, request, timeout):
        assert request.full_url.startswith(ORIGIN + '/api/v1/')
        self.calls.append(request)
        self.client.cookies.clear()
        headers = dict(request.header_items()) | {'X-Forwarded-For': '198.51.100.40', 'Host': 'nexus.example'}
        result = self.client.request(request.method, request.full_url, content=request.data, headers=headers)
        message = Message()
        for key, value in result.headers.multi_items():
            message.add_header(key, value)
        if self.after and request.full_url.endswith(self.after):
            self.after = None
            raise URLError('Injected lost reply')
        body = BytesIO(result.content)
        body.headers = message
        if result.status_code >= 400:
            raise HTTPError(request.full_url, result.status_code, 'Server response', message, body)
        return body


@pytest.fixture
def remote(work, monkeypatch, tmp_path):
    t = work
    t.app.state.operator_auth.configure(**ACCOUNT, local=True)
    vault, bridge = MemoryVault(), HTTPBridge(t.setup[2])
    monkeypatch.setattr(operator_client, 'open_backend', lambda: vault)
    monkeypatch.setattr(operator_client, 'build_opener', lambda *args: bridge)
    profile = OperatorProfile(tmp_path / 'operator-client', 'remote')
    profile.login(ORIGIN, **ACCOUNT)
    return SimpleNamespace(t=t, vault=vault, bridge=bridge, profile=profile)


def project(remote):
    saved = []
    r = remote
    selection = r.t.connection['selection'] | dict(operator_profile='remote', create_agent=False,
        binding_id=r.t.binding['binding_id'], project='operator-local-shortcut')
    flow = RemoteTerminalConnection(r.profile.client(), lambda value: saved.append(value))
    assert flow.review(selection)['state'] == 'configured'
    return saved[-1]


def test_remote_operator_work_and_lost_reply_use_canonical_subject_without_admin_credential(remote):
    r, saved = remote, []
    connection = project(r)
    flow = TerminalWork(r.profile.client(), lambda value: saved.append(json.loads(json.dumps(value))), connection)
    r.bridge.after = '/runtime/operations'
    with pytest.raises(ConnectionError) as lost:
        flow.submit('Explicit remote project request')
    assert lost.value.possible_effect
    reopened = TerminalWork(r.profile.client(), lambda value: None, connection, saved[-1])
    operation = reopened.resume()
    work_fixtures.complete(r.t, operation)
    assert reopened.observe()['state'] == 'completed'
    assert r.t.native.opens == 1 and len(r.t.native.native.sent) == 1
    token = next(iter(r.vault.values.values()))
    assert token not in json.dumps(saved) and token not in json.dumps(connection)
    assert token not in r.profile.path.read_text() and ACCOUNT['password'] not in r.profile.path.read_text()
    assert token not in repr(r.t.native.native.sent)
    assert all(token not in (request.data or b'').decode() for request in r.bridge.calls)
    with r.t.deps.connection_factory.unit_of_work(write=False) as uow:
        assert {tuple(row) for row in uow.connection.execute('SELECT actor_agent_id,subject_agent_id FROM execution_operations')} == {('operator', 'subject')}


def test_remote_profile_reuse_selects_remote_before_any_local_service(remote, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli import connect, work as cli
    r = remote
    def forbidden(*args):
        raise AssertionError('Remote topology must never resolve or start a local Server')
    monkeypatch.setattr(connect, 'resolve_local_service', forbidden)
    monkeypatch.setattr(cli, 'resolve_local_service', forbidden)
    args = ['--home', str(r.profile.home), '--profile', 'project', '--json']
    assert connect.run_connect(args + ['--operator-profile', 'remote', '--agent', 'subject',
                                      '--binding-id', r.t.binding['binding_id']]) == 0
    assert json.loads(capsys.readouterr().out)['topology'] == 'remote_operator'
    assert connect.run_connect(args) == 0  # Topology is recovered from the project profile.
    capsys.readouterr()
    assert cli.run_work(['sessions', *args]) == 0
    assert json.loads(capsys.readouterr().out)['sessions'] == []
    assert not (r.profile.home / 'nexus.db').exists()
    assert not (r.profile.home / 'service-context.json').exists()
    # An unreachable origin does not permit fallback, identity reset or launch.
    def unreachable(*args, **kwargs):
        raise URLError('offline')
    monkeypatch.setattr(r.bridge, 'open', unreachable)
    assert connect.run_connect(args) == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'SERVER_UNREACHABLE'
    assert not (r.profile.home / 'nexus.db').exists() and r.t.native.opens == 0


def test_remote_human_renews_and_answers_native_permission_without_agent_key(remote):
    from nexus_connector_core import RuntimeEvent
    from test_terminal_authorization import disable_grants
    r, replies = remote, []
    r.t.deps.config.feature_hitl = True
    connection = project(r)
    disable_grants(r.t, 'expired')
    flow = TerminalWork(r.profile.client(), lambda value: None, connection)
    review = flow.authorization_review()
    assert flow.authorize(approval=review['review_revision'])['state'] == 'authorization_committed'
    operation = flow.submit('Ask the operator before proceeding')
    work_fixtures.wait_receipt(r.t.setup, {'operation_id': operation['submission_turn_operation_id']})
    async def reply(request, decision, response):
        replies.append((decision, response))
    r.t.native.native.reply_native_approval = reply
    with r.t.deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    request = dict(schema_version=1, request_id=55, request_hash='d' * 64,
        method='item/commandExecution/requestApproval',
        params={'threadId': 'native-thread', 'turnId': 'turn-from-native', 'itemId': 'item'})
    r.t.setup[2].portal.call(r.t.native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
        stream['session_id'], stream['stream_epoch'], 0, 'approval_request', request['method'],
        {'native_approval': request, 'native_approval_display': dict(request)}, operation['submission_turn_operation_id']))
    deadline = time.monotonic() + 20
    while not (pending := flow.observe()['requests']['items']):
        assert time.monotonic() < deadline
        time.sleep(.03)
    proposal = pending[0]['request_payload']['kwargs']
    flow.decide(pending[0]['approval_id'], 'approve', reviewed_revision=document_revision(proposal))
    while not replies:
        assert time.monotonic() < deadline
        time.sleep(.03)
    assert replies == [('accept', None)]
    assert all(not any(key.lower() in ('authorization', 'x-api-key') for key, value in request.header_items()) for request in r.bridge.calls)


def test_failed_vault_write_revokes_new_login_and_preserves_previous_session(remote, monkeypatch):
    r = remote
    before = dict(r.vault.values), r.profile.path.read_bytes()
    def fail(*args):
        raise OSError('Injected vault failure')
    monkeypatch.setattr(r.vault, 'set', fail)
    with pytest.raises(ConnectionError) as failed:
        r.profile.login(ORIGIN, **ACCOUNT)
    assert failed.value.code == 'OPERATOR_VAULT_UNAVAILABLE'
    assert (dict(r.vault.values), r.profile.path.read_bytes()) == before
    assert r.profile.client().verify()['agent_id'] == 'operator'
    with r.t.app.state.operator_auth.db() as db:
        assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 1
    with pytest.raises(ConnectionError):
        OperatorProfile(r.profile.home, 'another', backend=r.vault).secret('get', ORIGIN)


def test_cookie_expiry_never_falls_back_to_loopback_or_agent_key(remote):
    r = remote
    token = next(iter(r.vault.values.values()))
    r.t.app.state.operator_auth.logout(token)
    with pytest.raises(ConnectionError) as expired:
        r.profile.client().verify()
    assert expired.value.code == 'OPERATOR_LOGIN_REQUIRED'
    # The header is an additional restriction, including on an open local Server.
    headers = {'X-Nexus-UI': '1', 'X-Nexus-Operator-Session-Required': '1'}
    r.t.setup[2].cookies.clear()
    assert r.t.setup[2].get('/api/v1/agents', headers=headers).status_code == 401
    assert r.t.setup[2].get('/api/v1/agents', headers=headers | r.t.setup[3]['subject']).status_code == 401
    assert not r.t.setup[2].get('/api/v1/operator-auth/status', headers=headers).json()['data']['local']
    assert r.t.setup[2].post('/api/v1/operator-auth/account', headers=headers, json=ACCOUNT).status_code == 403
    assert r.t.native.opens == 0


def test_profile_pins_origin_and_server_identity_and_never_serializes_password(remote):
    r = remote
    before = r.profile.path.read_bytes()
    with pytest.raises(ConnectionError) as conflict:
        r.profile.login('https://another.example', **ACCOUNT)
    assert conflict.value.code == 'PROFILE_CONFLICT'
    assert r.profile.path.read_bytes() == before
    client = r.profile.client()
    client.server_id = 'different-installation'
    with pytest.raises(ConnectionError) as changed:
        client.verify()
    assert changed.value.code == 'SERVER_ID_MISMATCH'
    assert ACCOUNT['password'] not in before.decode()
    assert OperatorProfile(r.profile.home, 'different', backend=r.vault).path != r.profile.path


def test_cli_login_status_logout_and_missing_vault_are_redacted(remote, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli.operator import run_operator
    r = remote
    args = ['--home', str(r.profile.home), '--profile', 'remote']
    monkeypatch.setattr('sys.stdin', StringIO(ACCOUNT['password'] + '\n'))
    assert run_operator(['login', *args, '--server', ORIGIN, '--username', 'human', '--password-stdin']) == 0
    token = next(iter(r.vault.values.values()))
    assert run_operator(['status', *args]) == 0
    assert run_operator(['logout', *args]) == 0
    assert not r.vault.values
    assert run_operator(['status', *args]) == 3
    output = capsys.readouterr().out
    assert token not in output and ACCOUNT['password'] not in output
    assert 'signed_out_locally' in output


@pytest.mark.parametrize('origin', ['http://nexus.example', 'https://user:secret@nexus.example',
    'https://nexus.example/path', 'https://nexus.example/?key=secret', 'https://nexus.example/#secret',
    'https://nexus.example\\evil', 'https://nexus.example:0', ' https://nexus.example'])
def test_unsafe_origins_are_rejected_before_transport(origin):
    with pytest.raises(ConnectionError) as refused:
        server_origin(origin)
    assert refused.value.code == 'SERVER_ORIGIN_INVALID'


def test_redirect_does_not_send_operator_cookie_to_other_origin():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(302)
            self.send_header('Location', f'http://localhost:{self.server.server_port}/stolen')
            self.end_headers()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        call = RemoteOperatorHTTP(f'http://127.0.0.1:{server.server_port}', token='a' * 43)
        with pytest.raises(ConnectionError):
            call('GET', '/api/v1/agents')
        assert seen == ['/api/v1/agents']
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_offline_logout_removes_local_session_without_claiming_remote_revocation(remote, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli.operator import run_operator
    r = remote
    token = next(iter(r.vault.values.values()))
    def unavailable(*args, **kwargs):
        raise URLError('offline')
    monkeypatch.setattr(r.bridge, 'open', unavailable)
    assert run_operator(['logout', '--home', str(r.profile.home), '--profile', 'remote']) == 3
    result = capsys.readouterr().out
    assert json.loads(result)['remote_revocation'] == 'unconfirmed'
    assert not r.vault.values and r.profile.path.exists()
    assert r.t.app.state.operator_auth.resolve(token) == 'human'
    assert token not in result and ACCOUNT['password'] not in result
