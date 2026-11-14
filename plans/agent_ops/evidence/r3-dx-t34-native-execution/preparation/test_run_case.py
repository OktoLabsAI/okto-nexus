import hashlib
import io
import json
from pathlib import Path
import queue
import sqlite3
import subprocess
from types import SimpleNamespace
import zipfile

import pytest
import run_case as case


class Reader:
    def __init__(self):
        self.lines = queue.Queue()
    def readline(self, limit):
        return self.lines.get()
    def close(self):
        pass


class Peer:
    pid = 1234
    def __init__(self, account=None, config=None, exit_timeout=False):
        self.account = account if account is not None else {'account': None, 'requiresOpenaiAuth': True}
        self.config = config if config is not None else {'config': {'cli_auth_credentials_store': 'file', 'model_provider': 'openai'}}
        self.stdout, self.stderr = Reader(), io.BytesIO(b'')
        self.stdin = self
        self.calls, self.closed, self.exit_timeout = [], False, exit_timeout
    def write(self, data):
        value = json.loads(data)
        self.calls.append(value)
        method = value['method']
        assert method in {'initialize', 'initialized', 'config/read', 'account/read'}
        if method == 'initialized':
            return
        response = self.account if method == 'account/read' else self.config if method == 'config/read' else {}
        self.stdout.lines.put((json.dumps({'id': value['id'], 'result': response}) + '\n').encode())
    def flush(self):
        pass
    def close(self):
        self.closed = True
        self.stdout.lines.put(b'')
    def wait(self, timeout):
        assert self.closed
        if self.exit_timeout:
            raise subprocess.TimeoutExpired('fixture', timeout)
        return 0


def test_preflight_has_only_three_read_rpcs_and_normal_eof(tmp_path):
    peer = Peer()
    kwargs = {}
    def spawn(argv, **options):
        kwargs.update(argv=argv, **options)
        return peer
    result = case.preflight(tmp_path / 'codex.exe', tmp_path, {'HOME': str(tmp_path)}, popen=spawn)
    assert result['methods'] == ['initialize', 'config/read', 'account/read']
    assert result['model_turns'] == 0 and result['physical_exit_observed']
    assert peer.calls[-1]['params'] == {'refreshToken': False}
    assert kwargs['env'] == {'HOME': str(tmp_path)}
    assert kwargs['argv'] == [str(tmp_path / 'codex.exe'), 'app-server']
    assert peer.closed


@pytest.mark.parametrize('account', [
    {}, {'requiresOpenaiAuth': True}, {'account': None, 'requiresOpenaiAuth': False},
    {'account': None, 'requiresOpenaiAuth': 'true'},
    {'account': {'type': 'chatgpt', 'email': 'PRIVATE_DO_NOT_PUBLISH'}, 'requiresOpenaiAuth': True},
])
def test_preflight_absence_must_be_explicit_and_no_account_data_leaks(tmp_path, account):
    peer = Peer(account=account)
    with pytest.raises(case.Refused, match='MISSING_LOGIN_NOT_PROVED') as caught:
        case.preflight(tmp_path / 'codex.exe', tmp_path, {}, popen=lambda *a, **k: peer)
    assert 'PRIVATE_DO_NOT_PUBLISH' not in str(caught.value)
    assert peer.closed and len(peer.calls) == 4


@pytest.mark.parametrize('config', [
    {}, {'config': {}}, {'config': {'cli_auth_credentials_store': 'keyring'}},
    {'config': {'cli_auth_credentials_store': 'auto'}},
    {'config': {'cli_auth_credentials_store': 'file', 'model_provider': 'custom'}},
])
def test_preflight_refuses_store_or_provider_before_reading_account(tmp_path, config):
    peer = Peer(config=config)
    with pytest.raises(case.Refused):
        case.preflight(tmp_path / 'codex.exe', tmp_path, {}, popen=lambda *a, **k: peer)
    assert peer.closed and not any(v['method'] == 'account/read' for v in peer.calls)


def test_preflight_eof_timeout_never_claims_exit_or_uses_kill(tmp_path):
    peer = Peer(exit_timeout=True)
    with pytest.raises(case.Refused, match='NATIVE_EOF_EXIT_UNCONFIRMED_PID_1234'):
        case.preflight(tmp_path / 'codex.exe', tmp_path, {}, popen=lambda *a, **k: peer)
    assert peer.closed  # No terminate/kill method exists on the fixture.


def test_environment_does_not_inherit_auth_or_personal_paths(tmp_path):
    env = case.environment(tmp_path, tmp_path/'venv', tmp_path/'native/codex.exe', {
        'SYSTEMROOT': 'C:/Windows', 'WINDIR': 'C:/Windows', 'PATH': 'personal-bin',
        'HOME': 'personal', 'CODEX_HOME': 'personal-codex', 'APPDATA': 'personal-appdata',
        'OPENAI_API_KEY': 'do-not-copy', 'CODEX_API_KEY': 'do-not-copy', 'ANTHROPIC_API_KEY': 'do-not-copy',
        'HTTP_PROXY': 'secret-proxy', 'PYTHONPATH': 'personal-python'})
    assert set(env).isdisjoint({'OPENAI_API_KEY', 'CODEX_API_KEY', 'ANTHROPIC_API_KEY', 'HTTP_PROXY', 'PYTHONPATH'})
    assert not any('personal' in value or 'do-not-copy' in value for value in env.values())
    assert env['CODEX_HOME'] == str(tmp_path/'profile/.codex')


def test_exclusive_reservation_cannot_replay(tmp_path):
    target = tmp_path/'reservation.json'
    case.write_once(target, {'once': 1})
    with pytest.raises(FileExistsError):
        case.write_once(target, {'once': 2})
    assert json.loads(target.read_bytes()) == {'once': 1}


def test_review_binds_home_scope_and_auth_context(tmp_path):
    review = {'state': 'review', 'review_revision': 'abc',
        'selection': {'candidate_ref': 'selected', 'agent': case.PROFILE},
        'request': {'broadcast_handoff_auto_claim': False, 'configuration': {
            'provider_home': str(tmp_path/'profile/.codex'), 'workspace_root': str(tmp_path/'project'),
            'adapter_id': 'codex_app_server', 'harness_settings': {}, 'secret_bindings': {},
            'authorization': {'minutes': 60, 'no_expiry': False, 'actions': 20, 'unlimited_actions': False}}}}
    assert case.validate_review(review, {'candidate_ref': 'selected'}, tmp_path) == 'abc'
    review['request']['configuration']['provider_home'] = 'C:/personal'
    with pytest.raises(case.Refused, match='SETUP_PATH_CHANGED'):
        case.validate_review(review, {'candidate_ref': 'selected'}, tmp_path)


def test_public_auth_failure_requires_completed_cleanup_and_concrete_guidance(tmp_path):
    value = dict(state='test_failed', error_code='PROVIDER_AUTH_REQUIRED', work_state='not_submitted',
        test={'retryable_failure': True}, setup_run_id='case',
        next_action='Use ' + str(tmp_path/'profile/.codex') + ' then codex login')
    assert case.validate_failure(value, tmp_path)['error_code'] == 'PROVIDER_AUTH_REQUIRED'
    value['test']['retryable_failure'] = False
    with pytest.raises(case.Refused, match='SETUP_CLEANUP_UNCONFIRMED'):
        case.validate_failure(value, tmp_path)


@pytest.mark.parametrize('with_turn', [False, True])
def test_journal_requires_failed_open_and_zero_turns(tmp_path, with_turn):
    directory = tmp_path/'nexus-home/connection-tests/own'
    directory.mkdir(parents=True)
    with sqlite3.connect(directory/'journal.db') as db:
        db.execute('CREATE TABLE operations_v2(operation_id,stage,error_code,possible_effect,retry_safe)')
        db.execute('CREATE TABLE operation_actions(action)')
        db.execute("INSERT INTO operations_v2 VALUES('open','FAILED','PROVIDER_AUTH_REQUIRED',1,0)")
        if with_turn:
            db.execute("INSERT INTO operation_actions VALUES('turn.submit')")
    if with_turn:
        with pytest.raises(case.Refused, match='AUTH_FAILURE_OR_ZERO_TURN_UNCONFIRMED'):
            case.journal_proof(tmp_path)
    else:
        assert case.journal_proof(tmp_path)['turn_actions'] == 0


def test_installed_payload_must_match_wheel(tmp_path):
    site = tmp_path/'venv/Lib/site-packages'
    pins = {}
    for package, key in [('okto_nexus', 'nexus_wheel'), ('nexus_connector_core', 'core_wheel')]:
        path = tmp_path/(key+'.whl')
        with zipfile.ZipFile(path, 'w') as wheel:
            wheel.writestr(package+'/__init__.py', 'PINNED')
        target = site/package/'__init__.py'
        target.parent.mkdir(parents=True)
        target.write_text('PINNED')
        pins[key] = {'path': str(path)}
    assert case.verify_installed({'pins': pins}, tmp_path/'venv')['files_equal_to_pinned_wheels'] == 2
    (site/'okto_nexus/__init__.py').write_text('STALE')
    with pytest.raises(case.Refused, match='INSTALLED_PAYLOAD_MISMATCH'):
        case.verify_installed({'pins': pins}, tmp_path/'venv')


def test_proposal_hash_and_every_runtime_pin_are_required(tmp_path, monkeypatch):
    monkeypatch.setattr(case, 'BASE', tmp_path)
    pinned = tmp_path/'driver.py'
    pinned.write_text('inert')
    monkeypatch.setattr(case, '__file__', str(pinned))
    expected_native = 'ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f'
    original_sha = case.sha
    native = tmp_path / 'native.exe'
    native.write_bytes(b'fake native, never executed')
    monkeypatch.setattr(case, 'sha', lambda p: expected_native if Path(p) == native else original_sha(p))
    proposal = {'root': str(tmp_path), 'status': 'OFFLINE_QUALIFIED_PENDING_ROOT_EXECUTION', 'native_version': '0.157.0',
        'model_turn_limit': 0, 'pins': {'driver': {'path': str(pinned), 'sha256': case.sha(pinned)},
            'native': {'path': str(native), 'sha256': expected_native}}}
    path = tmp_path/'proposal.json'
    path.write_text(json.dumps(proposal))
    digest = case.sha(path)
    assert case.load(digest) == proposal
    with pytest.raises(case.Refused, match='PROPOSAL_REVIEW_MISMATCH'):
        case.load('0'*64)
    pinned.write_text('changed')
    with pytest.raises(case.Refused, match='PIN_MISMATCH'):
        case.load(digest)
