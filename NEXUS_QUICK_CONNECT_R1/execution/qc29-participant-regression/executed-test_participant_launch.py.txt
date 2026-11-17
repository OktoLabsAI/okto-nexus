"""Real participant auth/files and foreground process boundaries with isolated credentials."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import test_participant_init
from test_connection_setup_recovery import snapshot
from okto_nexus.application.participant_launch import ParticipantLaunch
from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus.adapters.outbound import participant_process, participant_files
from okto_nexus.adapters.outbound.service_manager.context import atomic_json
from okto_nexus.adapters.inbound.cli.main import main

local_setup = test_participant_init.local_setup
setup = test_participant_init.setup


@pytest.fixture
def launch(setup, monkeypatch):
    s = setup
    reviewed = s.flow.review(s.selection, s.key)
    s.flow.apply(reviewed, s.key, reviewed['review_revision'])
    saved = s.saves[-1]
    participant_files.private_directory(s.home / 'terminal/participants')
    atomic_json(s.home / 'terminal/participants/external.json', saved)
    records, calls = [], []
    def spawn(context, environment):
        calls.append((deepcopy(context), dict(environment)))
        return SimpleNamespace(pid=1234, wait=lambda: 0)
    monkeypatch.setattr(participant_process, 'spawn', spawn)
    flow = ParticipantLaunch(s.home, 'external', lambda value: records.append(deepcopy(value)))
    return SimpleNamespace(s=s, saved=saved, flow=flow, records=records, calls=calls,
        env=dict(os.environ), executable=sys.executable)


def test_review_launch_replay_has_scoped_environment_and_no_server_mutation(launch):
    t = launch
    t.env.update(NEXUS_PARTICIPANT_TOKEN_OTHER='must-not-pass', nexus_participant_token_lower='must-not-pass')
    original = dict(t.env)
    intent = t.flow.review(t.saved, t.executable, environment=t.env)
    assert not t.calls and t.s.key not in json.dumps(t.records)
    result = t.flow.apply(intent, t.saved, intent['review_revision'], environment=t.env)
    assert result['state'] == 'exited' and result['exit_code'] == 0
    assert result['proof']['credential_delivery'] == 'supplied_to_owned_spawn'
    assert result['proof']['mcp'] == result['proof']['credential_in_client'] == 'UNKNOWN'
    assert result['proof']['work'] == 'NOT_SUBMITTED'
    reference = intent['review']['credential_reference']
    assert t.calls[0][1][reference] == t.s.key
    assert [k for k in t.calls[0][1] if k.upper().startswith('NEXUS_PARTICIPANT_TOKEN_')] == [reference]
    assert t.calls[0][0]['arguments'] == [] and t.env == original
    assert t.s.key not in json.dumps(t.records) and t.s.key not in json.dumps(result)
    assert snapshot(t.s.deps) == t.s.before and t.s.vault.writes == 1
    assert [v['state'] for v in t.records] == ['review', 'starting', 'started', 'exited']
    repeated = t.flow.apply(t.records[-1], t.saved, intent['review_revision'], environment={})
    assert repeated == result and len(t.calls) == 1


@pytest.mark.parametrize('change', ['config', 'context', 'project', 'binary', 'policy', 'approval'])
def test_drift_refuses_before_process_effect(launch, monkeypatch, change):
    t = launch
    intent = t.flow.review(t.saved, t.executable, environment=t.env)
    approval = intent['review_revision']
    if change == 'config':
        path = Path(t.s.selection['config_file'])
        path.write_bytes(path.read_bytes() + b'\n')
    elif change == 'context':
        t.env['CLAUDE_CONFIG_DIR'] = str(t.s.root / 'other-home')
    elif change in ('project', 'binary'):
        original = participant_process.launch_context
        def changed(*args, **kwargs):
            value = original(*args, **kwargs)
            value[change] = {'changed': True}
            return value
        monkeypatch.setattr(participant_process, 'launch_context', changed)
    elif change == 'policy':
        with t.s.deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("INSERT OR REPLACE INTO agent_connection_methods(agent_id,method,enabled) VALUES ('subject','mcp',0)")
    else:
        approval = 'wrong'
    with pytest.raises(ConnectionError):
        t.flow.apply(intent, t.saved, approval, environment=t.env)
    assert not t.calls and len(t.records) == 1


@pytest.mark.parametrize('stage,spawn_count', [('starting', 0), ('started', 1), ('exited', 1)])
def test_checkpoint_loss_preserves_uncertainty_without_respawn(launch, stage, spawn_count):
    t = launch
    intent = t.flow.review(t.saved, t.executable, environment=t.env)
    persist = t.flow.save
    def fail(value):
        if value['state'] == stage:
            raise OSError('private details ' + t.s.key)
        persist(value)
    t.flow.save = fail
    with pytest.raises(OSError):
        t.flow.apply(intent, t.saved, intent['review_revision'], environment=t.env)
    assert len(t.calls) == spawn_count
    t.flow.save = persist
    if stage != 'starting':
        retained = t.records[-1]
        result = t.flow.apply(retained, t.saved, intent['review_revision'], environment=t.env)
        assert result['state'] in ('starting', 'started')
        assert len(t.calls) == spawn_count
    assert t.s.key not in json.dumps(t.records)


def test_spawn_failure_never_retries_automatically_and_new_review_is_explicit(launch, monkeypatch):
    t = launch
    intent = t.flow.review(t.saved, t.executable, environment=t.env)
    def fail(*args):
        t.calls.append('attempt')
        raise OSError('private ' + t.s.key)
    monkeypatch.setattr(participant_process, 'spawn', fail)
    with pytest.raises(OSError):
        t.flow.apply(intent, t.saved, intent['review_revision'], environment=t.env)
    retained = t.records[-1]
    result = t.flow.apply(retained, t.saved, intent['review_revision'], environment=t.env)
    assert result['state'] == 'starting' and len(t.calls) == 1
    new = t.flow.review(t.saved, t.executable, environment=t.env, previous=retained)
    assert new['review_revision'] != intent['review_revision']
    assert new['review']['previous']['state'] == 'starting'
    assert len(t.calls) == 1


def test_wait_interruption_retains_started_checkpoint(launch, monkeypatch):
    t = launch
    def wait():
        raise KeyboardInterrupt()
    monkeypatch.setattr(participant_process, 'spawn', lambda *args: SimpleNamespace(pid=1234, wait=wait))
    intent = t.flow.review(t.saved, t.executable, environment=t.env)
    with pytest.raises(KeyboardInterrupt):
        t.flow.apply(intent, t.saved, intent['review_revision'], environment=t.env)
    assert t.records[-1]['state'] == 'started'


@pytest.mark.parametrize('client,selected', [('codex', False), ('codex', True), ('claude', True)])
def test_client_configuration_selection_preserves_daemon_and_file_boundary(setup, client, selected):
    s = setup
    config_file = s.root / ('custom.json' if client == 'claude' else 'custom.toml' if selected else '.codex/config.toml')
    selection = s.selection | dict(client=client, config_file=str(config_file), selected_file=selected)
    reviewed = s.flow.review(selection, s.key)
    s.flow.apply(reviewed, s.key, reviewed['review_revision'])
    saved = s.saves[-1]
    flow = ParticipantLaunch(s.home, 'external', lambda _: None)
    if client == 'codex' and selected:
        with pytest.raises(ConnectionError, match='config.toml'):
            flow.review(saved, sys.executable, environment=dict(os.environ))
    else:
        intent = flow.review(saved, sys.executable, environment=dict(os.environ))
        args = intent['review']['process']['arguments']
        assert args == (['--no-daemon'] if client == 'codex' else ['--mcp-config', str(config_file)])


def test_missing_profile_has_no_filesystem_effect(tmp_path, capsys):
    home = tmp_path / 'absent'
    assert main(['participant', 'launch', '--home', str(home), '--profile', 'absent', '--json']) == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'PARTICIPANT_PROFILE_ABSENT'
    assert not home.exists()


def test_cli_saved_plan_is_passive_and_replay_does_not_launch(launch, monkeypatch, capsys):
    t = launch
    base = ['participant', 'launch', '--home', str(t.s.home), '--profile', 'external', '--json']
    assert main([*base, '--plan', '--executable', t.executable]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert not t.calls
    get = t.s.vault.get
    def fail(*args):
        raise RuntimeError('Vault must not be accessed for saved plan')
    monkeypatch.setattr(t.s.vault, 'get', fail)
    assert main([*base, '--plan']) == 0
    assert json.loads(capsys.readouterr().out) == plan
    monkeypatch.setattr(t.s.vault, 'get', get)
    assert main([*base, '--approve', plan['review_revision']]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'exited' and len(t.calls) == 1
    assert main([*base, '--approve', plan['review_revision']]) == 0
    assert json.loads(capsys.readouterr().out) == result and len(t.calls) == 1
    assert main([*base, '--new', '--plan']) == 0
    assert json.loads(capsys.readouterr().out)['review_revision'] != plan['review_revision']


def test_cli_does_not_echo_process_errors_or_secrets(launch, monkeypatch, capsys):
    t = launch
    base = ['participant', 'launch', '--home', str(t.s.home), '--profile', 'external', '--json']
    assert main([*base, '--plan', '--executable', t.executable]) == 0
    plan = json.loads(capsys.readouterr().out)
    def fail(*args):
        raise OSError('SECRET ' + t.s.key)
    monkeypatch.setattr(participant_process, 'spawn', fail)
    assert main([*base, '--approve', plan['review_revision']]) == 3
    raw = capsys.readouterr().out
    assert t.s.key not in raw and 'SECRET' not in raw
    assert json.loads(raw)['code'] == 'PARTICIPANT_LAUNCH_UNCONFIRMED'


def test_real_subprocess_receives_reference_without_parent_mutation(setup, tmp_path):
    s = setup
    reviewed = s.flow.review(s.selection, s.key)
    _, config = s.flow.validate(reviewed)
    script, output = tmp_path / 'child.py', tmp_path / 'observed.json'
    script.write_text('import hashlib,json,os,sys\n'
        'value=os.environ.get(sys.argv[1], "")\n'
        'json.dump({"matched":hashlib.sha256(value.encode()).hexdigest()==sys.argv[2],'
        '"other_absent":"NEXUS_PARTICIPANT_TOKEN_OTHER" not in os.environ},open(sys.argv[3],"w"))\n')
    parent = dict(os.environ) | {'NEXUS_PARTICIPANT_TOKEN_OTHER': 'not-delivered'}
    before = dict(parent)
    env = participant_process.child_environment(config, s.key, parent)
    context = dict(executable=sys.executable, arguments=[str(script), config.credential_environment,
        hashlib.sha256(s.key.encode()).hexdigest(), str(output)], cwd=str(tmp_path))
    proc = participant_process.spawn(context, env)
    assert proc.wait(timeout=10) == 0
    assert json.loads(output.read_text()) == {'matched': True, 'other_absent': True}
    assert parent == before and s.key not in script.read_text() and s.key not in output.read_text()
