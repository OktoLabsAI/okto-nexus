"""Real participant HTTP/auth/SQLite with temporary files and a synthetic vault."""
from copy import deepcopy
from email.message import Message
from io import BytesIO, StringIO
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

import test_local_realization
from test_connection_setup import request_for, finish
from test_connection_setup_recovery import snapshot
from okto_nexus.application.execution_local_realizations import directory_identity
from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus.application.terminal_participant import TerminalParticipant
from okto_nexus.adapters.outbound import participant_client, participant_files
from okto_nexus.adapters.inbound.cli import participant

local_setup = test_local_realization.local_setup
ORIGIN = 'https://nexus.example'


class MemoryVault:
    def __init__(self):
        self.values, self.writes = {}, 0

    def set(self, service, name, value):
        self.values[service, name] = value
        self.writes += 1

    def get(self, service, name):
        return self.values[service, name]


class HTTPBridge:
    def __init__(self, client):
        self.client, self.calls = client, []

    def open(self, request, timeout):
        assert request.full_url.startswith(ORIGIN + '/v1/connections/participant?')
        assert request.method == 'GET' and request.data is None
        self.calls.append(request)
        self.client.cookies.clear()
        result = self.client.get(request.full_url, headers=dict(request.header_items()) |
            {'X-Forwarded-For': '198.51.100.40', 'Host': 'nexus.example'})
        headers = Message()
        for key, value in result.headers.multi_items():
            headers.add_header(key, value)
        body = BytesIO(result.content)
        body.headers, body.status = headers, result.status_code
        if result.status_code >= 400:
            raise HTTPError(request.full_url, result.status_code, 'Server response', headers, body)
        return body


@pytest.fixture
def setup(local_setup, tmp_path, monkeypatch):
    deps, app, client, headers, _, _, root = local_setup
    context, request = request_for(local_setup)
    binding = finish(local_setup, context, request,
        verified={'root': directory_identity(str(root)), 'home': None})['binding']
    vault, bridge = MemoryVault(), HTTPBridge(client)
    monkeypatch.setattr(participant_client, 'open_backend', lambda: vault)
    monkeypatch.setattr(participant_client, 'build_opener', lambda *args: bridge)
    saves = []
    flow = TerminalParticipant(tmp_path / 'participant-home', 'external', lambda value: saves.append(deepcopy(value)))
    selection = dict(server=ORIGIN, agent='subject', workspace_id=binding['workspace_id'], client='claude',
        client_version=None, entry_name='nexus', project=str(root), selected_file=False, config_file=str(root / '.mcp.json'))
    return SimpleNamespace(flow=flow, selection=selection, saves=saves, vault=vault, bridge=bridge,
        key=headers['subject']['Authorization'].split()[1], before=snapshot(deps), deps=deps,
        client=client, headers=headers, root=root, home=flow.home)


def test_review_apply_reconnect_preserves_runtime_and_other_configuration(setup):
    s = setup
    path = Path(s.selection['config_file'])
    raw = b'{"mcpServers":{"other":{"command":"never-executed","env":{"TOKEN":"other-secret"}}},"theme":"dark"}'
    path.write_bytes(raw)
    before_acl = participant_files.access_revision(path)
    saved = s.flow.review(s.selection, s.key)
    assert path.read_bytes() == raw and not s.vault.values
    assert s.key not in json.dumps(saved) and 'other-secret' not in json.dumps(saved)
    result = s.flow.apply(saved, s.key, saved['review_revision'])
    assert result['state'] == 'configuration_applied'
    assert result['proof'] == dict(identity='PASS', client_entry='PASS', credential_in_client='UNKNOWN',
        client_reload='UNKNOWN', mcp='UNKNOWN', work='NOT_SUBMITTED')
    assert participant_files.access_revision(path) == before_acl
    assert json.loads(path.read_bytes())['mcpServers']['other'] == json.loads(raw)['mcpServers']['other']
    backups = list(path.parent.glob('*.bak'))
    assert len(backups) == 1 and backups[0].read_bytes() == raw
    participant_files._check_private(backups[0])
    assert s.vault.writes == 1 and snapshot(s.deps) == s.before
    assert s.key not in path.read_text() and s.key not in json.dumps(s.saves)
    # Reconnect permits unrelated later edits, never repeats apply or rewrites them.
    path.write_bytes(path.read_bytes().replace(b'dark', b'light'))
    final = path.read_bytes()
    repeated = s.flow.apply(s.saves[-1], s.key, saved['review_revision'])
    assert repeated['state'] == 'configuration_applied'
    assert path.read_bytes() == final and s.vault.writes == 1 and len(list(path.parent.glob('*.bak'))) == 1
    assert [item['state'] for item in s.saves] == ['review', 'credential_pending', 'credential_stored', 'file_pending', 'done']


@pytest.mark.parametrize('actor,status', [('subject', 200), ('operator', 403), (None, 401)])
def test_participant_context_uses_bearer_identity_without_self_elevation(setup, actor, status):
    s = setup
    response = s.client.get('/v1/connections/participant', params={'workspace_id': s.selection['workspace_id']},
        headers=s.headers[actor] if actor else {})
    assert response.status_code == status, response.text
    if actor == 'subject':
        assert response.json()['agent_id'] == 'subject'
        assert str(s.root) not in response.text
        assert response.headers['cache-control'] == 'no-store'
    assert snapshot(s.deps) == s.before


def test_workspace_and_identity_mismatch_refused_without_local_effect(setup):
    s = setup
    for selection in (s.selection | {'workspace_id': 'absent'}, s.selection | {'agent': 'another'}):
        with pytest.raises(ConnectionError):
            s.flow.review(selection, s.key)
    assert not s.saves and not s.vault.values and snapshot(s.deps) == s.before


@pytest.mark.parametrize('change', ['file', 'approval', 'policy', 'review'])
def test_review_drift_blocks_before_vault_or_file_effect(setup, change):
    s = setup
    saved = s.flow.review(s.selection, s.key)
    revision = saved['review_revision']
    if change == 'file':
        Path(s.selection['config_file']).write_text('{"someone":"edited"}')
    elif change == 'approval':
        revision = 'wrong'
    elif change == 'review':
        saved['review']['selection']['agent'] = 'another'
    else:
        with s.deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("INSERT OR REPLACE INTO agent_connection_methods(agent_id,method,enabled) VALUES ('subject','mcp',0)")
    with pytest.raises(ConnectionError):
        s.flow.apply(saved, s.key, revision)
    assert not s.vault.values and not list(s.root.glob('*.bak'))


@pytest.mark.parametrize('lost_stage', ['credential_stored', 'done'])
def test_lost_checkpoint_resumes_same_intent_by_observing_effect(setup, lost_stage):
    s = setup
    path = Path(s.selection['config_file'])
    path.write_text('{"existing":true}')
    saved = s.flow.review(s.selection, s.key)
    persist = s.flow.save
    def fail(value):
        if value['state'] == lost_stage:
            raise OSError('Injected lost checkpoint')
        persist(value)
    s.flow.save = fail
    with pytest.raises(OSError):
        s.flow.apply(saved, s.key, saved['review_revision'])
    pending = s.saves[-1]
    assert pending['state'] == ('credential_pending' if lost_stage == 'credential_stored' else 'file_pending')
    s.flow.save = persist
    key = s.flow.key(pending, None)
    result = s.flow.apply(pending, key, pending['review_revision'])
    assert result['state'] == 'configuration_applied'
    assert s.saves[-1]['review']['setup_run_id'] == saved['review']['setup_run_id']
    assert len(list(s.root.glob('*.bak'))) == 1
    assert snapshot(s.deps) == s.before
    assert result['file_result']['recovered'] == (lost_stage == 'done')


def test_vault_failure_leaves_file_and_server_intact_and_retains_intent(setup, monkeypatch):
    s = setup
    saved = s.flow.review(s.selection, s.key)
    def fail(*args):
        raise RuntimeError('Injected private failure ' + s.key)
    monkeypatch.setattr(s.vault, 'set', fail)
    with pytest.raises(ConnectionError, match='protected participant') as error:
        s.flow.apply(saved, s.key, saved['review_revision'])
    assert s.key not in str(error.value)
    assert s.saves[-1]['state'] == 'credential_pending'
    assert not Path(s.selection['config_file']).exists() and snapshot(s.deps) == s.before


def test_uncertain_file_with_later_edit_is_preserved_without_new_intent(setup):
    s = setup
    saved = s.flow.review(s.selection, s.key)
    persist = s.flow.save
    def fail_after_replace(value):
        if value['state'] == 'done':
            raise OSError('Lost completion')
        persist(value)
    s.flow.save = fail_after_replace
    with pytest.raises(OSError):
        s.flow.apply(saved, s.key, saved['review_revision'])
    pending = s.saves[-1]
    path = Path(s.selection['config_file'])
    path.write_bytes(path.read_bytes() + b'\n')
    edited = path.read_bytes()
    s.flow.save = persist
    with pytest.raises(ConnectionError, match='changed'):
        s.flow.apply(pending, s.key, pending['review_revision'])
    assert s.saves[-1] == pending and path.read_bytes() == edited
    assert s.vault.writes == 1 and snapshot(s.deps) == s.before


@pytest.mark.parametrize('client', ['claude', 'codex', 'generic'])
def test_init_and_connect_participant_share_review_and_cli_checkpoints(setup, monkeypatch, capsys, client):
    from okto_nexus.adapters.inbound.cli.main import main
    s = setup
    base = ['--mode', 'participant', '--home', str(s.home), '--profile', 'cli', '--json']
    monkeypatch.setattr(participant.sys, 'stdin', StringIO(s.key + '\n'))
    args = ['--project', str(s.root), '--client', client, '--server', ORIGIN, '--agent', 'subject',
        '--workspace-id', s.selection['workspace_id']]
    assert main(['init', *base, *args, '--plan', '--key-stdin']) == 0
    review = json.loads(capsys.readouterr().out)
    assert not s.vault.values
    monkeypatch.setenv('SYNTHETIC_PARTICIPANT_INPUT', s.key)
    assert main(['connect', *base, '--approve', review['review_revision'], '--key-env', 'SYNTHETIC_PARTICIPANT_INPUT']) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied['state'] == ('manual_configuration_required' if client == 'generic' else 'configuration_applied')
    profile = s.home / 'terminal/participants/cli.json'
    assert s.key not in profile.read_text() and s.key not in json.dumps(applied)
    assert main(['connect', *base]) == 0
    assert json.loads(capsys.readouterr().out)['setup_run_id'] == review['setup_run_id']
    assert s.vault.writes == 1


def test_cli_never_falls_back_to_echoing_key(setup, monkeypatch, capsys):
    s = setup
    class Terminal(StringIO):
        def isatty(self):
            return True
    def unsafe_prompt(*args):
        import warnings
        warnings.warn('No controlling terminal', participant.getpass.GetPassWarning)
        pytest.fail('Echoing fallback must be interrupted')
    monkeypatch.setattr(participant.sys, 'stdin', Terminal())
    monkeypatch.setattr(participant.getpass, 'getpass', unsafe_prompt)
    assert participant.run_participant(['--home', str(s.home), '--profile', 'hidden', '--json', '--plan',
        '--project', str(s.root), '--server', ORIGIN, '--agent', 'subject', '--workspace-id', s.selection['workspace_id'],
        '--client', 'claude']) == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'PARTICIPANT_KEY_REQUIRED'
    assert not s.vault.values


def test_completed_entry_drift_and_approved_refresh_are_refused(setup, monkeypatch, capsys):
    s = setup
    monkeypatch.setattr(participant.sys, 'stdin', StringIO(s.key))
    base = ['--home', str(s.home), '--profile', 'kept', '--json']
    assert participant.run_participant(base + ['--server', ORIGIN, '--agent', 'subject',
        '--workspace-id', s.selection['workspace_id'], '--project', str(s.root), '--client', 'claude',
        '--plan', '--key-stdin']) == 0
    rev = json.loads(capsys.readouterr().out)['review_revision']
    monkeypatch.setattr(participant.sys, 'stdin', StringIO(s.key))
    assert participant.run_participant(base + ['--approve', rev, '--key-stdin']) == 0
    capsys.readouterr()
    assert participant.run_participant(base + ['--refresh', '--plan']) == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'SETUP_ALREADY_APPROVED'
    path = s.root / '.mcp.json'
    path.write_bytes(path.read_bytes().replace(b'nexus.example', b'changed.example'))
    edited = path.read_bytes()
    assert participant.run_participant(base) == 3
    capsys.readouterr()
    assert path.read_bytes() == edited and s.vault.writes == 1


@pytest.mark.parametrize('payload', [{'error': 'unsafe-shape'}, {'error': {'code': 'not-a-code'}}])
def test_malformed_http_errors_never_echo_response_or_key(monkeypatch, payload):
    secret = 'nxs_' + 'a' * 48
    def refuse(request, timeout):
        raise HTTPError(request.full_url, 400, 'private diagnostic', Message(), BytesIO(json.dumps(payload).encode()))
    monkeypatch.setattr(participant_client, 'build_opener', lambda *args: SimpleNamespace(open=refuse))
    with pytest.raises(ConnectionError) as error:
        participant_client.ParticipantHTTP(ORIGIN, secret, 'subject').context('workspace')
    assert error.value.code == 'REQUEST_REFUSED'
    assert secret not in str(error.value) and 'private diagnostic' not in str(error.value)


def test_actual_http_redirect_does_not_forward_bearer(monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from urllib.request import build_opener
    secret, received = 'nxs_' + 'a' * 48, []
    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.path, self.headers.get('Authorization')))
            self.send_response(302)
            self.send_header('Location', '/redirect-target')
            self.end_headers()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(participant_client, 'build_opener', build_opener)
        with pytest.raises(ConnectionError) as error:
            participant_client.ParticipantHTTP(f'http://127.0.0.1:{server.server_port}', secret, 'subject').context('workspace')
        assert error.value.code == 'SERVER_REDIRECT_REFUSED'
        assert len(received) == 1 and received[0][1] == 'Bearer ' + secret
        assert received[0][0].startswith('/v1/connections/participant?')
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()
