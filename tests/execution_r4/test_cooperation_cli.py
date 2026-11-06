"""Cooperation CLI with real TCP/SQLite and disposable participant identities.

Peer replies and claim/completion are authenticated canonical calls made by the
test client. They qualify identity cooperation, never a provider or harness.
Only explicit transport/persistence failure boundaries are injected.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import okto_nexus
import pytest

import test_coordination_cli as coordination
from test_cooperation_reply_read import snapshot as database_snapshot
from test_hitl import _attach, _rule
from test_pr34_remediation import tool
from okto_nexus.adapters.inbound.cli import cooperation as cooperation_cli
from okto_nexus.adapters.inbound.cli.main import main
from okto_nexus.adapters.outbound import cooperation_files
from okto_nexus.adapters.outbound.cooperation_files import CooperationFiles
from okto_nexus.adapters.outbound.participant_coordination_mcp import ParticipantMCP
from okto_nexus.adapters.outbound.service_manager.context import atomic_json
from okto_nexus.adapters.outbound.service_manager.locking import ExclusiveFileLock, LockBusy
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.application.terminal_connection import ConnectionError, document_revision


cli = coordination.cli
runtime = coordination.runtime
pytestmark = pytest.mark.parametrize('runtime', [False], indirect=True)


def snapshot(cli):
    return database_snapshot(cli.deps)


def base(cli, *, key=True):
    args = ['--home', str(cli.home), '--profile', cli.profile, '--json']
    return args + (['--key-env', coordination.KEY_ENV] if key else [])


def invoke(cli, capsys, action, *args, key=True):
    code = main(['participant', 'smoke', action, *args, *base(cli, key=key and action != 'status')])
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1, captured.out
    value = json.loads(captured.out)
    assert value['format'] == 1 and value['exit_code'] == code
    assert type(value['possible_effect']) is bool
    assert cli.caller not in captured.out + captured.err and cli.worker_key not in captured.out + captured.err
    return code, value


def files(cli):
    return {path.relative_to(cli.home): path.read_bytes() for path in cli.home.rglob('*') if path.is_file()}


def document(cli, identity=None):
    candidates = list((cli.home / 'terminal/cooperation' / cli.profile / 'attempts').glob('*/smoke.json'))
    for path in candidates:
        value = json.loads(path.read_text(encoding='utf-8'))
        if identity is None or value['smoke_id'] == identity:
            return path, value
    pytest.fail('The expected cooperation journal was not persisted')


def exchange(cli, capsys):
    code, review = invoke(cli, capsys, 'exchange', '--to', 'worker', '--plan')
    assert code == 0 and review['state'] == 'message_review'
    code, sent = invoke(cli, capsys, 'exchange', '--approve', review['review_revision'])
    assert code == 0 and sent['state'] == 'message_confirmed'
    return sent


def reply(cli, sent, *, legacy=False, parent=None):
    args = dict(workspace_id=cli.workspace, from_agent_id='worker',
        target={'strategy': 'direct', 'agent_id': 'caller'}, body='NEXUS_CONNECTION_OK private peer reply',
        parent_message_id=parent or sent['message_id'])
    if not legacy:
        args['client_request_id'] = sent['smoke_id'] + ':reply'
    result = tool(cli.client, cli.worker_key, 'message_create', args)
    assert result['ok'], result
    return result['data']['message_id']


def handoff_review(cli, capsys):
    sent = exchange(cli, capsys)
    reply(cli, sent)
    code, review = invoke(cli, capsys, 'handoff', '--plan')
    assert code == 0 and review['state'] == 'handoff_review'
    return review


def test_default_status_and_saved_exchange_review_are_local_only(cli, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Historical status and exchange review must not access credentials or the Server')
    monkeypatch.setattr(cooperation_cli, '_key', forbidden)
    monkeypatch.setattr(cooperation_cli, 'ParticipantHTTP', forbidden)
    monkeypatch.setattr(cooperation_cli, 'ParticipantMCP', forbidden)
    before, local = snapshot(cli), files(cli)
    code, missing = invoke(cli, capsys, 'status')
    assert code == 0 and missing['state'] == 'not_reviewed' and missing['historical']
    assert files(cli) == local and snapshot(cli) == before
    code, review = invoke(cli, capsys, 'exchange', '--to', 'worker', '--plan', key=False)
    assert code == 0 and review['consents'] == {'exchange': None, 'handoff': None}
    assert review['checks']['coordination_participation']['status'] == 'UNKNOWN'
    assert review['checks']['handoff_test']['status'] == 'UNKNOWN'
    assert 'provider cost' in json.dumps(review['review']['effects'])
    local = files(cli)
    for action, args in (('exchange', ['--plan']), ('status', [])):
        code, repeated = invoke(cli, capsys, action, *args, key=False)
        assert code == 0 and repeated['smoke_id'] == review['smoke_id']
        assert files(cli) == local and snapshot(cli) == before
    path, saved = document(cli)
    assert len(path.parent.name) == 64 and ':' not in path.parent.name
    assert saved['request_ids']['message_create'].endswith(':message')
    assert 'arguments' not in saved and 'body' not in path.read_text(encoding='utf-8')
    assert not (path.parent / 'requests').exists()


def test_separate_consents_canonical_reply_after_other_session_ack_and_claim_result(cli, capsys):
    initial_sessions = snapshot(cli)['sessions']
    code, review = invoke(cli, capsys, 'exchange', '--to', 'worker', '--plan')
    assert code == 0
    for phase, args in (('exchange', ['--approve', 'wrong-review']),
                        ('handoff', ['--approve', review['review_revision']]), ('handoff', ['--plan'])):
        before = snapshot(cli)
        code, refused = invoke(cli, capsys, phase, *args)
        assert code == 3 and refused['possible_effect'] is False
        assert snapshot(cli) == before
    code, sent = invoke(cli, capsys, 'exchange', '--approve', review['review_revision'])
    assert code == 0 and sent['checks']['coordination_participation']['status'] == 'UNKNOWN'
    assert snapshot(cli)['sessions'] == initial_sessions
    before = snapshot(cli)
    code, refused = invoke(cli, capsys, 'handoff', '--plan')
    assert code == 3 and refused['code'] == 'REVIEW_REQUIRED' and snapshot(cli) == before
    rid = reply(cli, sent)
    consumer = tool(cli.client, cli.caller, 'session_open', {'agent_id': 'caller', 'workspace_id': cli.workspace})
    assert consumer['ok'], consumer
    session = {key: consumer['data'][key] for key in ('session_id', 'session_secret')}
    assert tool(cli.client, cli.caller, 'inbox_pull', {'agent_id': 'caller', **session})['ok']
    assert tool(cli.client, cli.caller, 'inbox_ack', {'agent_id': 'caller', 'message_ids': [rid], **session})['ok']
    before = snapshot(cli)
    code, observed = invoke(cli, capsys, 'observe', '--timeout', '0')
    assert code == 0 and observed['state'] == 'exchange_proven' and observed['historical'] is False
    assert observed['qualification'] == 'identities_only'
    assert observed['evidence']['exchange']['reply_message_id'] == rid
    assert observed['checks']['coordination_participation']['status'] == 'PASS'
    assert observed['checks']['handoff_test']['status'] == 'UNKNOWN'
    assert snapshot(cli) == before
    code, planned = invoke(cli, capsys, 'handoff', '--plan')
    assert code == 0 and planned['reviews']['handoff'] != planned['reviews']['exchange']
    assert planned['consents']['handoff'] is None and snapshot(cli) == before
    code, refused = invoke(cli, capsys, 'handoff', '--approve', planned['reviews']['exchange'])
    assert code == 3 and refused['code'] == 'REVIEW_REQUIRED' and snapshot(cli) == before
    code, created = invoke(cli, capsys, 'handoff', '--approve', planned['review_revision'])
    assert code == 0 and created['handoff_id']
    before = snapshot(cli)
    code, resumed = invoke(cli, capsys, 'handoff')
    assert code == 0 and resumed['handoff_id'] == created['handoff_id'] and snapshot(cli) == before
    args = dict(workspace_id=cli.workspace, handoff_id=created['handoff_id'], agent_id='worker')
    claimed = tool(cli.client, cli.worker_key, 'handoff_claim', args)
    assert claimed['ok'], claimed
    completed = tool(cli.client, cli.worker_key, 'handoff_complete', args | {
        'claim_epoch': claimed['data']['claim_epoch'], 'result': 'Private canonical cooperation result'})
    assert completed['ok'], completed
    before = snapshot(cli)
    code, proven = invoke(cli, capsys, 'observe', '--timeout', '0')
    assert code == 0 and proven['state'] == 'handoff_proven' and proven['historical'] is False
    assert all(check['status'] == 'PASS' for check in proven['checks'].values())
    assert proven['evidence']['handoff']['claimed_by'] == 'worker' and snapshot(cli) == before
    code, history = invoke(cli, capsys, 'status')
    assert code == 0 and history['historical'] is True and history['qualification'] == 'identities_only'
    assert history['evidence'] == proven['evidence'] and snapshot(cli) == before
    persisted = b'\n'.join(files(cli).values())
    for secret in ('private peer reply', 'Private canonical cooperation result', cli.caller, cli.worker_key, session['session_secret']):
        assert secret.encode() not in persisted
    assert not (cli.home / 'terminal/coordination').exists() and not cli.peers


@pytest.mark.parametrize('kind', ['legacy', 'wrong_parent'])
def test_text_or_unrelated_reply_cannot_qualify_exchange(cli, capsys, kind):
    sent = exchange(cli, capsys)
    parent = None
    if kind == 'wrong_parent':
        other = tool(cli.client, cli.caller, 'message_create', dict(workspace_id=cli.workspace,
            from_agent_id='caller', target={'strategy': 'direct', 'agent_id': 'worker'}, body='Another conversation'))
        assert other['ok'], other
        parent = other['data']['message_id']
    reply(cli, sent, legacy=kind == 'legacy', parent=parent)
    before = snapshot(cli)
    code, unknown = invoke(cli, capsys, 'observe', '--timeout', '0')
    assert code == 4 and unknown['checks']['coordination_participation']['status'] == 'UNKNOWN'
    assert unknown['evidence']['exchange'] is None and snapshot(cli) == before
    code, refused = invoke(cli, capsys, 'handoff', '--plan')
    assert code == 3 and refused['code'] == 'REVIEW_REQUIRED' and snapshot(cli) == before


@pytest.mark.parametrize('phase', ['exchange', 'handoff'])
@pytest.mark.parametrize('lost_stage', ['response', 'journal'])
def test_lost_creation_confirmation_resumes_same_attempt_without_second_send(cli, capsys, monkeypatch, phase, lost_stage):
    if phase == 'handoff':
        review = handoff_review(cli, capsys)
    else:
        code, review = invoke(cli, capsys, 'exchange', '--to', 'worker', '--plan')
        assert code == 0
    operation = 'message_create' if phase == 'exchange' else 'handoff_create'
    productive = []
    original_call, original_save = ParticipantMCP.call, CooperationFiles.save
    def call(self, name, args, **kwargs):
        result = original_call(self, name, args, **kwargs)
        if name == operation:
            productive.append(args['client_request_id'])
            if lost_stage == 'response':
                raise ConnectionError('OUTCOME_UNKNOWN', 'Injected lost creation response.', possible_effect=True)
        return result
    def save(self, value):
        if lost_stage == 'journal' and value['receipts'][phase] is not None:
            raise OSError('Injected journal confirmation failure')
        return original_save(self, value)
    monkeypatch.setattr(ParticipantMCP, 'call', call)
    monkeypatch.setattr(CooperationFiles, 'save', save)
    code, uncertain = invoke(cli, capsys, phase, '--approve', review['review_revision'])
    assert code == 5 and uncertain['possible_effect'] is True
    assert productive == [review['request_ids'][operation]]
    assert document(cli)[1]['consents'][phase] == review['review_revision']
    before = snapshot(cli)
    monkeypatch.setattr(CooperationFiles, 'save', original_save)
    code, resumed = invoke(cli, capsys, phase)
    assert code == 0 and resumed['smoke_id'] == review['smoke_id']
    assert resumed['receipts'][phase]['state'] == 'created'
    assert productive == [review['request_ids'][operation]] and snapshot(cli) == before


def test_real_process_death_after_exchange_commit_recovers_installed_entrypoint(cli, capsys):
    code, review = invoke(cli, capsys, 'exchange', '--to', 'worker', '--plan')
    assert code == 0
    environment = {key: value for key, value in os.environ.items()
        if key.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP'}}
    environment.update({coordination.KEY_ENV: cli.caller, 'HOME': str(cli.home), 'USERPROFILE': str(cli.home),
        'PYTHONUTF8': '1', 'PYTHONPATH': str(Path(okto_nexus.__file__).resolve().parents[1])})
    crash = '''import os, sys
from okto_nexus.adapters.outbound.participant_coordination_mcp import ParticipantMCP
from okto_nexus.adapters.inbound.cli.main import main
original = ParticipantMCP.call
def lose(self, name, args, **kwargs):
    result = original(self, name, args, **kwargs)
    if name == 'message_create':
        os._exit(73)
    return result
ParticipantMCP.call = lose
raise SystemExit(main(sys.argv[1:]))
'''
    args = ['participant', 'smoke', 'exchange', '--approve', review['review_revision'], *base(cli)]
    died = subprocess.run([sys.executable, '-X', 'utf8', '-c', crash, *args], cwd=cli.project,
        env=environment, capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert died.returncode == 73, died.stderr
    assert not died.stdout
    path, saved = document(cli)
    assert saved['consents']['exchange'] == review['review_revision'] and saved['receipts']['exchange'] is None
    requests = [p for p in (path.parent / 'requests').glob('*.json') if p.name != 'latest.json']
    assert len(requests) == 1 and json.loads(requests[0].read_text(encoding='utf-8'))['state'] == 'uncertain'
    before = snapshot(cli)
    entrypoint = Path(sys.executable).with_name('okto-nexus.exe' if os.name == 'nt' else 'okto-nexus')
    resumed = subprocess.run([str(entrypoint), 'participant', 'smoke', 'exchange', *base(cli)],
        cwd=cli.project, env=environment, capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert resumed.returncode == 0, resumed.stderr
    value = json.loads(resumed.stdout)
    assert value['state'] == 'message_confirmed' and value['smoke_id'] == review['smoke_id']
    assert snapshot(cli) == before and len(before['messages']) == 1
    status = subprocess.run([str(entrypoint), 'participant', 'smoke', 'status', *base(cli, key=False)],
        cwd=cli.project, env=environment, capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert status.returncode == 0 and json.loads(status.stdout)['message_id'] == value['message_id']
    assert snapshot(cli) == before and cli.caller not in died.stderr + resumed.stdout + resumed.stderr + status.stdout + status.stderr


@pytest.mark.parametrize('phase', ['exchange', 'handoff'])
def test_pending_approval_is_retained_and_human_decision_recovers_same_request(cli, capsys, phase):
    if phase == 'handoff':
        review = handoff_review(cli, capsys)
    else:
        code, review = invoke(cli, capsys, 'exchange', '--to', 'worker', '--plan')
        assert code == 0
    operation = 'message_create' if phase == 'exchange' else 'handoff_create'
    cli.deps.config.feature_hitl = True
    _attach(cli.deps, 'caller', governance=[_rule(operation, 'require_approval')])
    code, pending = invoke(cli, capsys, phase, '--approve', review['review_revision'])
    assert code == 0 and pending['receipts'][phase]['state'] == 'pending_approval'
    approval_id = pending['receipts'][phase]['approval_id']
    before = snapshot(cli)
    code, repeated = invoke(cli, capsys, phase)
    assert code == 0 and repeated['receipts'][phase]['approval_id'] == approval_id and snapshot(cli) == before
    code, waiting = invoke(cli, capsys, 'observe', '--timeout', '0')
    assert code == 4 and waiting['receipts'][phase]['approval_id'] == approval_id and snapshot(cli) == before
    decision = cli.client.post('/api/v1/approvals/' + approval_id + '/decision',
        headers={'x-api-key': cli.runtime[4]}, json={'decision': 'approve'})
    assert decision.status_code == 200, decision.text
    before = snapshot(cli)
    code, recovered = invoke(cli, capsys, phase)
    assert code == 0 and recovered['receipts'][phase]['state'] == 'created'
    assert recovered['receipts'][phase]['approval_id'] == approval_id
    assert recovered['request_ids'][operation] == review['request_ids'][operation] and snapshot(cli) == before


def test_observing_old_attempt_does_not_replace_latest_or_ordinary_coordination_index(cli, capsys):
    code, ordinary = coordination.invoke(cli, capsys, 'message', 'send', *coordination.arguments(cli, 'message'))
    assert code == 0 and ordinary['message_id']
    ordinary_path = cli.home / 'terminal/coordination' / cli.profile / 'latest.json'
    ordinary_index = ordinary_path.read_bytes()
    old = exchange(cli, capsys)
    reply(cli, old)
    code, newer = invoke(cli, capsys, 'exchange', '--new', '--to', 'worker', '--plan')
    assert code == 0 and newer['smoke_id'] != old['smoke_id']
    index = cli.home / 'terminal/cooperation' / cli.profile / 'latest.json'
    latest = index.read_bytes()
    before = snapshot(cli)
    code, observed = invoke(cli, capsys, 'observe', '--attempt', old['smoke_id'], '--timeout', '0')
    assert code == 0 and observed['smoke_id'] == old['smoke_id']
    assert index.read_bytes() == latest and ordinary_path.read_bytes() == ordinary_index and snapshot(cli) == before
    code, current = invoke(cli, capsys, 'status')
    assert code == 0 and current['smoke_id'] == newer['smoke_id']


@pytest.mark.parametrize('failure', ['timeout', 'interrupt', 'network'])
def test_observe_is_passive_releases_profile_lock_and_excludes_same_attempt(cli, capsys, monkeypatch, failure):
    sent = exchange(cli, capsys)
    attempt_path, _ = document(cli)
    original = ParticipantMCP.call
    calls = []
    def probe(self, name, args, **kwargs):
        calls.append(name)
        if name in ('message_status', 'event_cursor', 'event_wait'):
            guard = ExclusiveFileLock(cli.profile_path.with_suffix('.guard'))
            guard.acquire()
            guard.release()
            held = ExclusiveFileLock(attempt_path.with_name('smoke.guard'))
            with pytest.raises(LockBusy):
                held.acquire()
        if name == 'event_wait' and failure != 'timeout':
            if failure == 'interrupt':
                raise KeyboardInterrupt()
            raise ConnectionError('MCP_RESPONSE_UNCONFIRMED', 'Injected lost read.')
        return original(self, name, args, **kwargs)
    monkeypatch.setattr(ParticipantMCP, 'call', probe)
    before = snapshot(cli)
    code, result = invoke(cli, capsys, 'observe', '--timeout', '0' if failure == 'timeout' else '30')
    assert code == {'timeout': 4, 'interrupt': 130, 'network': 5}[failure]
    assert result['smoke_id'] == sent['smoke_id'] and result['possible_effect'] is False
    assert set(calls) <= {'coordination_request_get', 'event_cursor', 'message_status', 'event_wait'}
    assert 'message_status' in calls and snapshot(cli) == before and not cli.peers
    guard = ExclusiveFileLock(attempt_path.with_name('smoke.guard'))
    guard.acquire()
    guard.release()


@pytest.mark.parametrize('change', ['workspace', 'profile', 'credential'])
def test_changed_profile_scope_or_revoked_credential_refuses_before_send(cli, capsys, change):
    code, review = invoke(cli, capsys, 'exchange', '--to', 'worker', '--plan')
    assert code == 0
    extra = []
    if change == 'workspace':
        extra = ['--workspace', 'other-workspace']
    elif change == 'profile':
        saved = json.loads(cli.profile_path.read_text(encoding='utf-8'))
        saved['review']['setup_run_id'] = 'different-participant-setup'
        saved['review_revision'] = document_revision(saved['review'])
        atomic_json(cli.profile_path, saved)
    else:
        with cli.deps.connection_factory.unit_of_work() as uow:
            AgentKeyAuthService(cli.deps.repos.agents, cli.deps.clock).issue_key(uow, agent_id='caller')
    before = snapshot(cli)
    code, refused = invoke(cli, capsys, 'exchange', '--approve', review['review_revision'], *extra)
    assert code == 3 and refused['state'] == 'refused' and refused['possible_effect'] is False
    assert snapshot(cli) == before and document(cli)[1]['consents']['exchange'] is None


def test_checkpoint_failure_before_consent_prevents_productive_transmission(cli, capsys, monkeypatch):
    code, review = invoke(cli, capsys, 'exchange', '--to', 'worker', '--plan')
    assert code == 0
    original, calls = ParticipantMCP.call, []
    def record(self, name, args, **kwargs):
        calls.append(name)
        return original(self, name, args, **kwargs)
    def fail(*args, **kwargs):
        raise OSError('Injected journal write failure')
    monkeypatch.setattr(ParticipantMCP, 'call', record)
    monkeypatch.setattr(cooperation_files, 'atomic_json', fail)
    before = snapshot(cli)
    code, refused = invoke(cli, capsys, 'exchange', '--approve', review['review_revision'])
    assert code == 3 and refused['code'] == 'CHECKPOINT_WRITE_FAILED' and refused['possible_effect'] is False
    assert not set(calls) & {'message_create', 'handoff_create'} and snapshot(cli) == before


@pytest.mark.parametrize('args', [
    ['status', '--key-env', coordination.KEY_ENV], ['status', '--key-stdin'],
    ['status', '--plan'], ['observe', '--to', 'worker'],
    ['handoff', '--new'], ['exchange', '--new', '--approve', 'revision'],
])
def test_invalid_creation_or_credential_flags_have_no_effect(cli, capsys, args):
    before, local = snapshot(cli), files(cli)
    with pytest.raises(SystemExit) as error:
        main(['participant', 'smoke', *args, *base(cli, key=False)])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert 'usage:' in captured.err.lower() and not captured.out
    assert snapshot(cli) == before and files(cli) == local


def test_doctor_reads_historical_proof_without_live_claims_credentials_or_effects(cli, capsys, monkeypatch):
    from okto_nexus.application import participant_diagnostics

    sent = exchange(cli, capsys)
    rid = reply(cli, sent)
    code, proof = invoke(cli, capsys, 'observe', '--timeout', '0')
    assert code == 0 and proof['evidence']['exchange']['reply_message_id'] == rid
    before, local = snapshot(cli), files(cli)

    def forbidden(*args, **kwargs):
        pytest.fail('Default doctor must read only historical local evidence')

    monkeypatch.setattr(cooperation_cli, '_key', forbidden)
    monkeypatch.setattr(coordination.TerminalParticipant, 'key', forbidden)
    monkeypatch.setattr(participant_diagnostics, 'ParticipantHTTP', forbidden)
    monkeypatch.setattr(participant_diagnostics, 'inspect_mcp', forbidden)
    code = main(['doctor', '--mode', 'participant', *base(cli, key=False)])
    captured = capsys.readouterr()
    assert code == 0 and len(captured.out.splitlines()) == 1
    result = json.loads(captured.out)
    checks = {check['id']: check for check in result['checks']}
    for level, previous in (('coordination_participation', 'PASS'), ('handoff_test', 'UNKNOWN')):
        assert checks[level]['status'] == 'UNKNOWN' and checks[level]['code'] == 'HISTORICAL_EVIDENCE_ONLY'
        evidence = checks[level]['evidence']
        assert evidence['source'] == 'local_receipt' and evidence['last_observed_status'] == previous
        assert evidence['smoke_id'] == sent['smoke_id'] and evidence['qualification'] == 'identities_only'
    assert checks['coordination_participation']['evidence']['observation'] == proof['evidence']['exchange']
    for level in ('client_reload', 'credential_environment', 'work_result'):
        assert checks[level]['status'] == 'UNKNOWN'
    assert result['effects']['credential_read'] is False and result['effects']['mcp_checked'] is False
    assert result['effects']['tools_called'] is False and result['effects']['work_submitted'] is False
    assert files(cli) == local and snapshot(cli) == before
    assert cli.caller not in captured.out + captured.err


@pytest.mark.parametrize('checkpoint', ['retained', 'missing'])
def test_revoked_credential_during_uncertain_resume_preserves_possible_effect_and_ids(cli, capsys, monkeypatch, checkpoint):
    code, review = invoke(cli, capsys, 'exchange', '--to', 'worker', '--plan')
    assert code == 0
    original = ParticipantMCP.call
    productive = []

    def lose(self, name, args, **kwargs):
        result = original(self, name, args, **kwargs)
        if name == 'message_create':
            productive.append(args['client_request_id'])
            raise ConnectionError('OUTCOME_UNKNOWN', 'Injected response loss after commit.', possible_effect=True)
        return result

    monkeypatch.setattr(ParticipantMCP, 'call', lose)
    code, lost = invoke(cli, capsys, 'exchange', '--approve', review['review_revision'])
    assert code == 5 and lost['possible_effect'] is True
    if checkpoint == 'missing':
        path, saved = document(cli)
        assert saved['consents']['exchange'] is not None and saved['receipts']['exchange'] is None
        requests = [p for p in (path.parent / 'requests').glob('*.json') if p.name != 'latest.json']
        assert len(requests) == 1
        requests[0].unlink()
    with cli.deps.connection_factory.unit_of_work() as uow:
        AgentKeyAuthService(cli.deps.repos.agents, cli.deps.clock).issue_key(uow, agent_id='caller')
    before, local = snapshot(cli), files(cli)
    code, refused = invoke(cli, capsys, 'exchange')
    assert code == 5 and refused['state'] == 'uncertain' and refused['possible_effect'] is True
    assert refused['smoke_id'] == review['smoke_id']
    assert refused['smoke']['request_ids'] == review['request_ids']
    assert productive == [review['request_ids']['message_create']]
    assert snapshot(cli) == before and files(cli) == local


@pytest.mark.parametrize('guard_state', ['absent', 'busy'])
def test_retained_plans_are_local_snapshots_with_missing_or_busy_guards(cli, capsys, monkeypatch, guard_state):
    review = handoff_review(cli, capsys)
    path, _ = document(cli)
    paths = [cli.profile_path.with_suffix('.guard'), path.with_name('smoke.guard')]
    held = []
    if guard_state == 'absent':
        for guard_path in paths:
            guard_path.unlink()
    before, local = snapshot(cli), files(cli)
    if guard_state == 'busy':
        for guard_path in paths:
            guard = ExclusiveFileLock(guard_path)
            guard.acquire()
            held.append(guard)

    def forbidden(*args, **kwargs):
        pytest.fail('A retained review must not acquire guards, credentials or a network client')

    for name in ('ExclusiveFileLock', '_key', 'ParticipantHTTP', 'ParticipantMCP'):
        monkeypatch.setattr(cooperation_cli, name, forbidden)
    try:
        for phase in ('exchange', 'handoff'):
            code, planned = invoke(cli, capsys, phase, '--plan', key=False)
            assert code == 0 and planned['smoke_id'] == review['smoke_id'] and planned['historical'] is True
            assert planned['review_revision'] == review['reviews'][phase]
            assert planned['consents']['handoff'] is None
            # Windows denies reads of the held lock region. Compare those
            # guard bytes before acquisition and after release; all other
            # bytes are compared immediately after each retained-plan read.
            current = {p.relative_to(cli.home): p.read_bytes() for p in cli.home.rglob('*')
                if p.is_file() and p not in paths}
            assert current == {p: value for p, value in local.items() if cli.home / p not in paths}
            assert snapshot(cli) == before
        if guard_state == 'absent':
            assert not any(guard_path.exists() for guard_path in paths)
    finally:
        for guard in held:
            guard.release()
    assert files(cli) == local
