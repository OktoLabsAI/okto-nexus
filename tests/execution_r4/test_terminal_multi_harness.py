"""UI016: canonical CLI/HTTP/SQLite journey with two synthetic adapter kinds.

The candidates are inert owned files, never executables. Existing terminal
fixtures replace discovery/version checks, availability qualification and the
provider setup test; lifecycle below is an explicit fake. This does not qualify
real Codex/Claude protocols, login, account usage, or service lifecycle.
"""
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from nexus_connector_core.discovery import fingerprint

import test_terminal_connect
from test_connection_setup_recovery import snapshot
from okto_nexus.adapters.inbound.cli import connect
from okto_nexus.adapters.outbound.service_manager.context import read_json
from okto_nexus.bootstrap import embedded_inventory

terminal = test_terminal_connect.terminal
checking = test_terminal_connect.checking
local_setup = test_terminal_connect.local_setup


@pytest.fixture
def two_harnesses(terminal, tmp_path, monkeypatch):
    t = terminal
    owner = t.app.state.embedded_inventory_owner
    codex = owner.candidates[0]
    claude_file = tmp_path / 'inert-claude-candidate.exe'
    claude_file.write_bytes(b'UI016 inert Claude fixture, never executable')
    claude = replace(codex, adapter_id='claude_stream', executable=str(claude_file),
        fingerprint=fingerprint(claude_file), version=None, trust='untrusted')
    candidates = (codex, claude)
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **kwargs:
        SimpleNamespace(candidates=tuple(c for c in candidates
            if not kwargs.get('adapter_ids') or c.adapter_id in kwargs['adapter_ids'])))
    return t


def stable_agent(deps, agent_id):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = dict(uow.connection.execute('SELECT * FROM agents WHERE agent_id=?', (agent_id,)).fetchone())
    row.pop('last_seen_at', None)
    return row


def test_single_observed_harness_needs_no_profile_and_existing_connection_offers_all_intents(
        terminal, local_setup, tmp_path, monkeypatch, capsys):
    t = terminal
    local_setup[2].portal.call(t.app.state.embedded_inventory_owner.refresh)
    assert {item.adapter_id for item in t.app.state.embedded_inventory_owner.candidates} == {'codex_app_server'}
    home = tmp_path / 'single-cli-home'
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=1),
        inspect=lambda: dict(state='ready', instance_id='synthetic-existing-instance'),
        ensure_running=lambda **kwargs: dict(state='ready', instance_id='synthetic-existing-instance'))
    monkeypatch.setattr(connect, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    prompts, answers = [], iter(['y'])

    def choose(prompt):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr('builtins.input', choose)
    command = ['--home', str(home), '--project', t.selection['project'], '--no-chat']
    assert connect.run_connect(command) == 0
    path, = (home / 'terminal/profiles').glob('*.json')
    connection = read_json(path)
    assert connection['state'] == 'done'
    assert connection['result']['binding']['adapter_id'] == 'codex_app_server'
    assert all('profile' not in prompt.lower() for prompt in prompts)
    before, profile_bytes = snapshot(t.deps), path.read_bytes()
    turns = tuple(t.turns)
    capsys.readouterr()
    answers = iter(['c'])
    assert connect.run_connect(command + ['--plan']) == 0
    output = capsys.readouterr().out
    assert 'Resume codex' in output and 'a. Add another connection' in output and 'c. Cancel' in output
    assert path.read_bytes() == profile_bytes and snapshot(t.deps) == before and tuple(t.turns) == turns


def test_two_distinct_harnesses_share_project_keep_custom_a_and_recover_b_finish(
        two_harnesses, local_setup, tmp_path, monkeypatch, capsys):
    t = two_harnesses
    local_setup[2].portal.call(t.app.state.embedded_inventory_owner.refresh)
    owner = t.app.state.embedded_inventory_owner
    assert {c.adapter_id for c in owner.candidates} == {'codex_app_server', 'claude_stream'}
    assert all(Path(c.executable).is_relative_to(tmp_path) for c in owner.candidates)
    t.call('POST', '/api/v1/agents', dict(agent_id='custom-codex-a', role='Chosen reviewer role',
        metadata={'display_name': 'Chosen Codex A'},
        permissions={'messages': {'send_broadcast': False}, 'limits': {'messages_per_minute': 7}}))
    home = tmp_path / 'cli-home'
    provider_home = tmp_path / 'owned-empty-claude-home'
    provider_home.mkdir()
    lifecycle = []
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=1),
        inspect=lambda: dict(state='ready', instance_id='synthetic-lifecycle-instance'),
        ensure_running=lambda **kwargs: lifecycle.append('reuse-same-instance') or
            dict(state='ready', instance_id='synthetic-lifecycle-instance'))
    monkeypatch.setattr(connect, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    prompts = []
    def run(client, answers, *options):
        values = iter(answers)
        def choose(prompt):
            prompts.append(prompt)
            return next(values)
        monkeypatch.setattr('builtins.input', choose)
        return connect.run_connect(['--home', str(home), '--project', t.selection['project'],
            '--client', client, '--no-chat', *options])

    assert run('codex', ['y'], '--agent', 'custom-codex-a') == 0
    profiles = home / 'terminal/profiles'
    first_path, = profiles.glob('*.json')
    first = read_json(first_path)
    assert first['selection']['agent'] == 'custom-codex-a'
    first_binding = first['result']['binding']
    settings_path = '/api/v1/harness/endpoints/' + first_binding['endpoint_id'] + '/harness-settings'
    settings = t.call('GET', settings_path)['data']
    updated = t.call('PUT', settings_path, dict(expected_revision=settings['revision'],
        settings={'model': 'ui016-custom-model'}, reissue_grants=False))['data']
    assert updated['settings'] == {'model': 'ui016-custom-model'}
    assert updated['grants_revoked'] == 1 and updated['grants_reissued'] == 0
    first_bytes = first_path.read_bytes()
    a_agent = stable_agent(t.deps, 'custom-codex-a')
    assert a_agent['role'] == 'Chosen reviewer role'
    assert json.loads(a_agent['permissions'])['limits']['messages_per_minute'] == 7
    a_canonical = t.flow.current('custom-codex-a', first_binding['binding_id'])
    assert a_canonical['public_config']['harness_settings'] == {'model': 'ui016-custom-model'}
    before = snapshot(t.deps)
    initial_tests = tuple(t.turns)
    assert len(initial_tests) == 1

    t.fault.after = 'setup:finish'
    assert run('claude', ['a', 'y'], '--provider-home', str(provider_home)) == 3
    second_path, = (p for p in profiles.glob('*.json') if p != first_path)
    pending = read_json(second_path)
    assert pending['state'] == 'finish'
    assert pending['review_request']['workspace_id'] == first_binding['workspace_id']
    assert pending['review_request']['configuration']['adapter_id'] == 'claude_stream'
    assert pending['selection']['agent'] != 'custom-codex-a'
    after_finish = snapshot(t.deps)
    assert len(t.turns) == 2
    assert all(row in after_finish['execution_bindings'] for row in before['execution_bindings'])
    assert all(row in after_finish['runtime_execution_grants'] for row in before['runtime_execution_grants'])
    assert first_path.read_bytes() == first_bytes
    assert stable_agent(t.deps, 'custom-codex-a') == a_agent
    assert t.flow.current('custom-codex-a', first_binding['binding_id']) == a_canonical

    assert run('claude', ['1'], '--provider-home', str(provider_home)) == 0
    recovered = read_json(second_path)
    assert recovered['state'] == 'done'
    assert recovered['request']['client_intent_id'] == pending['request']['client_intent_id']
    assert recovered['selection']['agent'] == pending['selection']['agent']
    assert recovered['result']['binding']['workspace_id'] == first_binding['workspace_id']
    assert recovered['result']['binding']['adapter_id'] == 'claude_stream'
    assert snapshot(t.deps) == after_finish and len(t.turns) == 2

    assert run('codex', ['1']) == 0
    assert first_path.read_bytes() == first_bytes
    assert snapshot(t.deps) == after_finish and len(t.turns) == 2
    assert stable_agent(t.deps, 'custom-codex-a') == a_agent
    assert t.flow.current('custom-codex-a', first_binding['binding_id']) == a_canonical
    # Cancel an additional review before consenting to its test/Finish.
    assert run('claude', ['a', 'n'], '--provider-home', str(provider_home)) == 0
    assert snapshot(t.deps) == after_finish and len(t.turns) == 2
    assert first_path.read_bytes() == first_bytes
    assert all('profile' not in prompt.lower() for prompt in prompts)
    assert all(item == 'reuse-same-instance' for item in lifecycle)
    assert {candidate.adapter_id for candidate in t.probes} == {'codex_app_server', 'claude_stream'}
    output = capsys.readouterr().out
    assert 'Connection shortcut:' in output
