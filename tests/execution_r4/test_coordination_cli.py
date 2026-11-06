"""Participant CLI over real TCP MCP/HTTP and SQLite, using disposable profiles.

Only explicit failure boundaries are injected. No provider, personal vault,
service registration or implicit canonical agent session is used.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import okto_nexus
import pytest

import test_pr34_remediation as fixtures
from test_pr34_remediation import tool
from test_hitl import _attach, _rule
from okto_nexus.adapters.inbound.cli import coordination as coordination_cli
from okto_nexus.adapters.inbound.cli.main import main
from okto_nexus.adapters.outbound import coordination_files, participant_client
from okto_nexus.adapters.outbound.coordination_files import CoordinationFiles
from okto_nexus.adapters.outbound.participant_coordination_mcp import ParticipantMCP
from okto_nexus.adapters.outbound.participant_files import private_directory
from okto_nexus.adapters.outbound.service_manager.context import atomic_json
from okto_nexus.adapters.outbound.service_manager.locking import ExclusiveFileLock
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus.application.terminal_participant import TerminalParticipant


runtime = fixtures.runtime
pytestmark = pytest.mark.parametrize('runtime', [False], indirect=True)
KEY_ENV = 'SYNTHETIC_COORDINATION_CLI_KEY'


@pytest.fixture
def cli(runtime, tmp_path, monkeypatch):
    deps, client, project, peers, operator, caller = runtime
    workspace = tool(client, caller, 'workspace_resolve', {'project_root': project})['data']['workspace_id']
    home, profile = tmp_path / 'participant-home', 'coordination'
    path = home / 'terminal/participants' / (profile + '.json')
    private_directory(path.parent)
    flow = TerminalParticipant(home, profile, lambda value: atomic_json(path, value))
    selection = dict(server=str(client.base_url).rstrip('/'), agent='caller', workspace_id=workspace,
        client='generic', client_version=None, entry_name='nexus', project=project,
        selected_file=False, config_file=None)
    flow.review(selection, caller)
    # init creates a persistent guard; keep the same profile lifecycle here.
    guard = ExclusiveFileLock(path.with_suffix('.guard'))
    guard.acquire()
    guard.release()
    monkeypatch.setenv(KEY_ENV, caller)
    monkeypatch.setattr(participant_client, 'open_backend',
        lambda: pytest.fail('Coordination with an explicit fixture key must not access a vault'))
    with deps.connection_factory.unit_of_work() as uow:
        worker_key = AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id='worker')
    return SimpleNamespace(runtime=runtime, deps=deps, client=client, project=Path(project),
        workspace=workspace, home=home, profile=profile, profile_path=path,
        caller=caller, worker_key=worker_key, peers=peers,
        base=['--home', str(home), '--profile', profile, '--key-env', KEY_ENV, '--json'])


def invoke(cli, capsys, command, action, *arguments):
    code = main([command, action, *arguments, *cli.base])
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 1, captured.out
    result = json.loads(lines[0])
    assert result['format'] == 1 and result['exit_code'] == code
    assert type(result['possible_effect']) is bool
    assert cli.caller not in captured.out + captured.err
    return code, result


def arguments(cli, operation, *, body='Private coordination content', identity=None, new=False):
    path = cli.project / ('message.md' if operation == 'message' else 'handoff.md')
    path.write_text(body, encoding='utf-8')
    result = ['--to', 'worker', '--workspace', cli.workspace, '--body-file', str(path)]
    result += ['--subject', 'Conversation'] if operation == 'message' else ['--title', 'Review implementation']
    if identity:
        result += ['--request-id', identity]
    if new:
        result += ['--new-request']
    return result


def snapshot(cli):
    with cli.deps.connection_factory.unit_of_work(write=False) as uow:
        return {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
            for table in ('agents', 'messages', 'message_deliveries', 'handoffs', 'approvals', 'coordination_requests',
                          'sessions', 'events', 'delivery_outbox', 'execution_operations')}


def checkpoints(cli):
    directory = cli.home / 'terminal/coordination' / cli.profile
    return [path for path in directory.glob('*.json') if path.name != 'latest.json']


@pytest.mark.parametrize('operation', ['message', 'handoff'])
def test_commands_resume_latest_and_explicit_new_request_preserve_private_content(cli, capsys, operation):
    command = 'send' if operation == 'message' else 'create'
    original_sessions = snapshot(cli)['sessions']
    args = arguments(cli, operation, identity='ticket:review-1', new=True)
    code, first = invoke(cli, capsys, operation, command, *args)
    assert code == 0 and first['state'] == 'created'
    identifier = first['message_id' if operation == 'message' else 'handoff_id']
    assert first['scope']['agent_id'] == 'caller'
    after = snapshot(cli)
    assert after['sessions'] == original_sessions and not cli.peers
    paths = checkpoints(cli)
    assert len(paths) == 1 and len(paths[0].stem) == 64 and ':' not in paths[0].name
    stored = paths[0].read_text(encoding='utf-8')
    assert 'ticket:review-1' in stored
    assert 'Private coordination content' not in stored and 'Review implementation' not in stored
    assert cli.caller not in stored and 'Conversation' not in stored

    # A fresh command object resumes the latest request without another send.
    code, repeated = invoke(cli, capsys, operation, command, *arguments(cli, operation))
    assert code == 0 and repeated['client_request_id'] == first['client_request_id']
    assert repeated['message_id' if operation == 'message' else 'handoff_id'] == identifier
    assert snapshot(cli) == after
    code, inspected = invoke(cli, capsys, 'request', 'inspect', first['client_request_id'])
    assert code == 0 and inspected['request_receipt'] == first['request_receipt']
    assert snapshot(cli) == after

    code, conflict = invoke(cli, capsys, operation, command, *arguments(cli, operation, body='Changed content'))
    assert code == 3 and conflict['code'] == 'REQUEST_CONFLICT'
    assert snapshot(cli) == after
    code, new = invoke(cli, capsys, operation, command, *arguments(cli, operation, body='New work', new=True))
    assert code == 0 and new['client_request_id'] != first['client_request_id']
    assert new['message_id' if operation == 'message' else 'handoff_id'] != identifier
    assert len(checkpoints(cli)) == 2 and snapshot(cli)['sessions'] == original_sessions


@pytest.mark.parametrize('lost_stage', ['response', 'checkpoint'])
def test_lost_creation_result_recovers_after_cli_restart_without_second_productive_call(cli, capsys, monkeypatch, lost_stage):
    original_call, original_save = ParticipantMCP.call, CoordinationFiles.save
    productive = []

    def call(self, name, arguments, **kwargs):
        result = original_call(self, name, arguments, **kwargs)
        if name == 'message_create':
            productive.append(arguments['client_request_id'])
            if lost_stage == 'response':
                raise ConnectionError('OUTCOME_UNKNOWN', 'Injected response loss.', possible_effect=True)
        return result

    def save(self, value):
        if lost_stage == 'checkpoint' and value['state'] == 'confirmed':
            raise OSError('Injected checkpoint failure')
        return original_save(self, value)

    monkeypatch.setattr(ParticipantMCP, 'call', call)
    monkeypatch.setattr(CoordinationFiles, 'save', save)
    args = arguments(cli, 'message')
    code, uncertain = invoke(cli, capsys, 'message', 'send', *args)
    assert code == 5 and uncertain['state'] == 'uncertain' and uncertain['possible_effect']
    assert len(productive) == 1
    stored = json.loads(checkpoints(cli)[0].read_text(encoding='utf-8'))
    assert stored['state'] == 'uncertain' and stored['client_request_id'] == uncertain['client_request_id']
    before = snapshot(cli)
    monkeypatch.setattr(CoordinationFiles, 'save', original_save)
    code, recovered = invoke(cli, capsys, 'message', 'send', *args)
    assert code == 0 and recovered['client_request_id'] == uncertain['client_request_id']
    assert len(productive) == 1 and snapshot(cli) == before


def test_real_process_death_after_commit_recovers_through_installed_entrypoint(cli):
    environment = {key: value for key, value in os.environ.items()
        if key.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP'}}
    environment.update({KEY_ENV: cli.caller, 'HOME': str(cli.home), 'USERPROFILE': str(cli.home),
        'PYTHONPATH': str(Path(okto_nexus.__file__).resolve().parents[1])})
    argv = ['message', 'send', *arguments(cli, 'message'), *cli.base]
    crash = '''import os, sys
from okto_nexus.adapters.outbound.participant_coordination_mcp import ParticipantMCP
from okto_nexus.adapters.inbound.cli.main import main
original = ParticipantMCP.call
def lose(self, tool, arguments, **kwargs):
    result = original(self, tool, arguments, **kwargs)
    if tool == 'message_create':
        os._exit(73)
    return result
ParticipantMCP.call = lose
raise SystemExit(main(sys.argv[1:]))
'''
    died = subprocess.run([sys.executable, '-X', 'utf8', '-c', crash, *argv], cwd=cli.project,
        env=environment, capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert died.returncode == 73, died.stderr
    assert not died.stdout and cli.caller not in died.stderr
    persisted = json.loads(checkpoints(cli)[0].read_text(encoding='utf-8'))
    assert persisted['state'] == 'uncertain'
    before = snapshot(cli)
    assert len(before['coordination_requests']) == 1 and len(before['messages']) == 1
    entrypoint = Path(sys.executable).with_name('okto-nexus.exe' if os.name == 'nt' else 'okto-nexus')
    assert entrypoint.is_file(), 'The tested package must expose its installed console entrypoint'
    environment['PYTHONUTF8'] = '1'
    resumed = subprocess.run([str(entrypoint), *argv], cwd=cli.project,
        env=environment, capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert resumed.returncode == 0, resumed.stderr
    result = json.loads(resumed.stdout)
    assert result['client_request_id'] == persisted['client_request_id'] and result['state'] == 'created'
    assert snapshot(cli) == before
    inspected = subprocess.run([str(entrypoint), 'request', 'inspect',
        result['client_request_id'], *cli.base], cwd=cli.project,
        env=environment, capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)['message_id'] == result['message_id']
    assert snapshot(cli) == before
    assert cli.caller not in resumed.stdout + resumed.stderr + inspected.stdout + inspected.stderr


def test_checkpoint_failure_precedes_productive_transmission(cli, capsys, monkeypatch):
    before, calls = snapshot(cli), []
    original = ParticipantMCP.call

    def record(self, name, arguments, **kwargs):
        calls.append(name)
        return original(self, name, arguments, **kwargs)

    def fail(*args, **kwargs):
        raise OSError('Injected pre-transmission checkpoint failure')

    monkeypatch.setattr(ParticipantMCP, 'call', record)
    monkeypatch.setattr(coordination_files, 'atomic_json', fail)
    code, refused = invoke(cli, capsys, 'message', 'send', *arguments(cli, 'message'))
    assert code == 3 and refused['possible_effect'] is False
    assert not set(calls) & {'message_create', 'handoff_create'}
    assert snapshot(cli) == before


def test_unknown_server_contract_refuses_before_checkpoint_or_creation(cli, capsys, monkeypatch):
    original = ParticipantMCP.discover

    def old(self):
        result = original(self)
        result['info']['coordination_requests'].pop('observed_at')
        return result

    monkeypatch.setattr(ParticipantMCP, 'discover', old)
    before = snapshot(cli)
    code, refused = invoke(cli, capsys, 'message', 'send', *arguments(cli, 'message'))
    assert code == 3 and refused['code'] == 'SERVER_UPGRADE_REQUIRED'
    assert not (cli.home / 'terminal/coordination').exists()
    assert snapshot(cli) == before


def test_create_with_wait_checks_passive_capability_before_creating_work(cli, capsys, monkeypatch):
    original = ParticipantMCP.discover

    def old(self):
        result = original(self)
        result['info'].pop('coordination_observation')
        return result

    monkeypatch.setattr(ParticipantMCP, 'discover', old)
    before = snapshot(cli)
    code, refused = invoke(cli, capsys, 'handoff', 'create', *arguments(cli, 'handoff'), '--wait')
    assert code == 3 and refused['code'] == 'SERVER_UPGRADE_REQUIRED'
    assert refused['possible_effect'] is False
    assert snapshot(cli) == before and not checkpoints(cli)


@pytest.mark.parametrize('operation', ['message', 'handoff'])
def test_explicit_session_context_survives_resume_without_storing_its_secret(cli, capsys, monkeypatch, operation):
    opened = tool(cli.client, cli.caller, 'session_open',
        dict(workspace_id=cli.workspace, agent_id='caller'))['data']
    monkeypatch.setenv('SYNTHETIC_COORDINATION_SESSION_PROOF', opened['session_secret'])
    action = 'send' if operation == 'message' else 'create'
    args = arguments(cli, operation)
    proof = ['--session-secret-env', 'SYNTHETIC_COORDINATION_SESSION_PROOF']
    code, first = invoke(cli, capsys, operation, action, *args,
        '--session-id', opened['session_id'], *proof)
    assert code == 0
    before = snapshot(cli)
    stored = json.loads(checkpoints(cli)[0].read_text(encoding='utf-8'))
    assert stored['context'] == {'from_session_id' if operation == 'message' else 'session_id': opened['session_id']}
    assert opened['session_secret'] not in json.dumps(stored) and cli.caller not in json.dumps(stored)
    # Omitted session ID on resume reuses the original context; it never opens a replacement.
    code, repeated = invoke(cli, capsys, operation, action, *args, *proof)
    assert code == 0 and repeated['client_request_id'] == first['client_request_id']
    assert snapshot(cli) == before


def test_pending_approval_wait_retains_original_request_until_human_decision(cli, capsys):
    cli.deps.config.feature_hitl = True
    _attach(cli.deps, 'caller', governance=[_rule('handoff_create', 'require_approval')])
    args = arguments(cli, 'handoff')
    code, pending = invoke(cli, capsys, 'handoff', 'create', *args, '--wait', '--timeout', '0')
    assert code == 4 and pending['state'] == 'timed_out' and pending['approval_id']
    assert not snapshot(cli)['handoffs']
    before = snapshot(cli)
    code, repeated = invoke(cli, capsys, 'handoff', 'create', *args, '--wait', '--timeout', '0')
    assert code == 4 and repeated['approval_id'] == pending['approval_id']
    assert repeated['client_request_id'] == pending['client_request_id'] and snapshot(cli) == before
    decision = cli.client.post('/api/v1/approvals/' + pending['approval_id'] + '/decision',
        headers={'x-api-key': cli.runtime[4]}, json={'decision': 'approve'})
    assert decision.status_code == 200, decision.text
    before = snapshot(cli)
    code, created = invoke(cli, capsys, 'handoff', 'create', *args)
    assert code == 0 and created['state'] == 'created'
    assert created['approval_id'] == pending['approval_id']
    assert created['client_request_id'] == pending['client_request_id'] and snapshot(cli) == before


def test_rotated_credential_cannot_resume_the_existing_request(cli, capsys):
    args = arguments(cli, 'message')
    code, first = invoke(cli, capsys, 'message', 'send', *args)
    assert code == 0
    with cli.deps.connection_factory.unit_of_work() as uow:
        AgentKeyAuthService(cli.deps.repos.agents, cli.deps.clock).issue_key(uow, agent_id='caller')
    before = snapshot(cli)
    code, refused = invoke(cli, capsys, 'message', 'send', *args)
    assert code == 3 and refused['state'] == 'refused'
    assert snapshot(cli) == before
    assert json.loads(checkpoints(cli)[0].read_text(encoding='utf-8'))['client_request_id'] == first['client_request_id']


@pytest.mark.parametrize('change', ['workspace', 'profile', 'server'])
def test_scope_or_profile_drift_refuses_before_creation(cli, capsys, monkeypatch, change):
    args, before = arguments(cli, 'message'), snapshot(cli)
    if change == 'workspace':
        args[args.index(cli.workspace)] = 'different-workspace'
    elif change == 'profile':
        saved = json.loads(cli.profile_path.read_text(encoding='utf-8'))
        saved['review']['selection']['agent'] = 'worker'
        atomic_json(cli.profile_path, saved)
    else:
        original = participant_client.ParticipantHTTP.context
        def different(self, workspace):
            return original(self, workspace) | {'server_id': 'different-server'}
        monkeypatch.setattr(participant_client.ParticipantHTTP, 'context', different)
    code, refused = invoke(cli, capsys, 'message', 'send', *args)
    assert code == 3 and refused['possible_effect'] is False
    assert refused['code'] in {'PROFILE_CONFLICT', 'PARTICIPANT_PROFILE_INVALID', 'SERVER_CHANGED'}
    assert snapshot(cli) == before and not checkpoints(cli)


@pytest.mark.parametrize('boundary', ['parent_link', 'private_acl'])
def test_profile_safety_boundary_refuses_before_guard_profile_key_or_http(cli, capsys, monkeypatch, boundary):
    """Targeted boundary injection; no real links or personal ACLs are changed."""
    before = snapshot(cli)
    original_profile = cli.profile_path.read_bytes()
    parent = cli.profile_path.parent
    checked = []

    def forbidden(*args, **kwargs):
        pytest.fail('Unsafe participant paths must be refused before guard/profile/key/HTTP access')

    for name in ('ExclusiveFileLock', 'read_json', '_key', 'ParticipantHTTP'):
        monkeypatch.setattr(coordination_cli, name, forbidden)
    if boundary == 'parent_link':
        # Simulate the platform link detector only for the selected directory.
        detector = 'is_junction' if os.name == 'nt' else 'is_symlink'
        original = getattr(Path, detector)
        monkeypatch.setattr(Path, detector, lambda path: path == parent or original(path))
        monkeypatch.setattr(coordination_cli, '_check_private', forbidden)
    else:
        def deny(path):
            checked.append(path)
            raise ConnectionError('PROFILE_PATH_UNSAFE', 'Injected unsafe private-directory permissions.')
        monkeypatch.setattr(coordination_cli, '_check_private', deny)
    code, refused = invoke(cli, capsys, 'message', 'send', *arguments(cli, 'message'))
    assert code == 3 and refused['code'] == 'PROFILE_PATH_UNSAFE'
    assert refused['possible_effect'] is False
    assert checked == ([parent] if boundary == 'private_acl' else [])
    assert cli.profile_path.read_bytes() == original_profile
    assert snapshot(cli) == before and not checkpoints(cli)


def test_request_inspect_missing_is_read_only_and_cannot_create_profile_or_checkpoint(cli, capsys):
    before = snapshot(cli)
    files = {path.relative_to(cli.home): path.read_bytes() for path in cli.home.rglob('*') if path.is_file()}
    code, value = invoke(cli, capsys, 'request', 'inspect', 'unknown:id', '--operation', 'message_create')
    assert code == 5 and value['code'] == 'NOT_FOUND' and value['possible_effect'] is True
    assert snapshot(cli) == before and not (cli.home / 'terminal/coordination').exists()
    after = {path.relative_to(cli.home): path.read_bytes() for path in cli.home.rglob('*') if path.is_file()}
    assert after == files


def test_handoff_create_wait_timeout_and_reopen_observation_are_passive(cli, capsys, monkeypatch):
    code, timeout = invoke(cli, capsys, 'handoff', 'create', *arguments(cli, 'handoff'), '--wait', '--timeout', '0')
    assert code == 4 and timeout['state'] == 'timed_out'
    handoff_id = timeout['handoff_id']
    assert timeout['handoff']['status'] == 'OPEN'
    before = snapshot(cli)
    unlocked = []
    original = ParticipantMCP.call

    def probe(self, name, arguments, **kwargs):
        if name in ('event_cursor', 'handoff_get', 'event_wait'):
            assert arguments['passive'] is True and arguments['workspace_id'] == cli.workspace
            assert arguments['agent_id'] == 'caller'
            guard = ExclusiveFileLock(cli.profile_path.with_suffix('.guard'))
            guard.acquire()
            guard.release()
            unlocked.append(name)
        return original(self, name, arguments, **kwargs)

    monkeypatch.setattr(ParticipantMCP, 'call', probe)
    code, repeated = invoke(cli, capsys, 'handoff', 'wait', handoff_id, '--timeout', '0')
    assert code == 4 and repeated['handoff_id'] == handoff_id
    assert unlocked == ['event_cursor', 'handoff_get']
    assert snapshot(cli) == before and not cli.peers


def test_completion_before_wait_is_returned_without_new_session_or_effect(cli, capsys):
    code, created = invoke(cli, capsys, 'handoff', 'create', *arguments(cli, 'handoff'))
    assert code == 0
    args = dict(workspace_id=cli.workspace, handoff_id=created['handoff_id'], agent_id='worker')
    claimed = tool(cli.client, cli.worker_key, 'handoff_claim', args)
    assert claimed['ok'], claimed
    completed = tool(cli.client, cli.worker_key, 'handoff_complete', args | {'result': 'Canonical completed result'})
    assert completed['ok'], completed
    before = snapshot(cli)
    code, result = invoke(cli, capsys, 'handoff', 'wait', created['handoff_id'], '--timeout', '0')
    assert code == 0 and result['state'] == 'completed'
    assert result['handoff']['result'] == 'Canonical completed result'
    assert snapshot(cli) == before and not cli.peers


@pytest.mark.parametrize('failure', ['interrupt', 'network'])
def test_wait_interrupt_or_unknown_read_does_not_cancel_or_resubmit(cli, capsys, monkeypatch, failure):
    code, created = invoke(cli, capsys, 'handoff', 'create', *arguments(cli, 'handoff'))
    assert code == 0
    original = ParticipantMCP.call
    calls = []
    def fail(self, name, arguments, **kwargs):
        calls.append(name)
        if name == 'event_wait':
            if failure == 'interrupt':
                raise KeyboardInterrupt()
            raise ConnectionError('MCP_RESPONSE_UNCONFIRMED', 'Injected lost read.', stage='coordination')
        return original(self, name, arguments, **kwargs)
    monkeypatch.setattr(ParticipantMCP, 'call', fail)
    before = snapshot(cli)
    # Leave enough budget for real TCP cursor/snapshot setup; the injected
    # failure itself occurs immediately when the long-poll would start.
    code, result = invoke(cli, capsys, 'handoff', 'wait', created['handoff_id'], '--timeout', '30')
    assert code == (130 if failure == 'interrupt' else 5)
    assert result['handoff_id'] == created['handoff_id'] and result['possible_effect'] is False
    assert set(calls) <= {'event_cursor', 'handoff_get', 'event_wait'}
    assert snapshot(cli) == before


@pytest.mark.parametrize('failure', ['interrupt', 'network'])
def test_create_wait_failure_keeps_confirmed_creation_and_checkpoint(cli, capsys, monkeypatch, failure):
    original = ParticipantMCP.call
    created = []

    def fail(self, name, arguments, **kwargs):
        if name == 'event_wait':
            if failure == 'interrupt':
                raise KeyboardInterrupt()
            raise ConnectionError('MCP_RESPONSE_UNCONFIRMED', 'Injected lost read.', stage='coordination')
        result = original(self, name, arguments, **kwargs)
        if name == 'handoff_create':
            created.append(result['handoff_id'])
        return result

    monkeypatch.setattr(ParticipantMCP, 'call', fail)
    args = arguments(cli, 'handoff')
    code, result = invoke(cli, capsys, 'handoff', 'create', *args, '--wait', '--timeout', '30')
    assert code == (130 if failure == 'interrupt' else 5)
    assert len(created) == 1 and result['handoff_id'] == created[0]
    assert result['creation']['handoff_id'] == created[0] and result['creation']['state'] == 'created'
    assert result['possible_effect'] is False
    persisted = json.loads(checkpoints(cli)[0].read_text(encoding='utf-8'))
    assert persisted['state'] == 'confirmed' and persisted['client_request_id'] == result['client_request_id']
    before = snapshot(cli)
    code, resumed = invoke(cli, capsys, 'handoff', 'create', *args)
    assert code == 0 and resumed['handoff_id'] == created[0] and len(created) == 1
    assert snapshot(cli) == before


@pytest.mark.parametrize('visibility', ['private', 'public'])
def test_handoff_visibility_is_preserved_by_canonical_creation(cli, capsys, visibility):
    sessions = snapshot(cli)['sessions']
    code, created = invoke(cli, capsys, 'handoff', 'create', *arguments(cli, 'handoff'),
        '--visibility', visibility)
    assert code == 0 and created['state'] == 'created'
    with cli.deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            'SELECT visibility FROM handoffs WHERE handoff_id=? AND workspace_id=?',
            (created['handoff_id'], cli.workspace)).fetchone()
    assert row is not None and row['visibility'] == visibility
    assert snapshot(cli)['sessions'] == sessions and not cli.peers


def test_workspace_visibility_is_rejected_before_any_server_effect(cli, capsys):
    before = snapshot(cli)
    with pytest.raises(SystemExit) as error:
        main(['handoff', 'create', *arguments(cli, 'handoff'), '--visibility', 'workspace', *cli.base])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert 'invalid choice' in captured.err and 'workspace' in captured.err and not captured.out
    assert snapshot(cli) == before and not checkpoints(cli)


@pytest.mark.parametrize('arguments', [
    ['message', 'send', '--from-agent-id', 'worker'],
    ['message', 'send', '--to', 'worker'],
    ['message', 'send', '--to', 'worker', '--body', 'text', '--target-json', '{}'],
    ['handoff', 'wait'],
    ['handoff', 'wait', 'handoff-id', '--timeout', 'nan'],
    ['handoff', 'wait', 'handoff-id', '--body', 'This is not a creation command'],
    ['handoff', 'wait', 'handoff-id', '--new-request'],
])
def test_usage_errors_have_exit_two_and_no_server_effect(cli, capsys, arguments):
    before = snapshot(cli)
    with pytest.raises(SystemExit) as error:
        main([*arguments, *cli.base])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert 'usage:' in captured.err.lower() and not captured.out
    assert snapshot(cli) == before and not checkpoints(cli)
