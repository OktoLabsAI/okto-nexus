"""Actual CLI/HTTP preset review, controlled Test/Finish and same-ID recovery."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

import test_terminal_connect
import test_remote_project_policy
import test_remote_operator_terminal as remote_helpers
from test_project_preset_update import revision_two
from test_connection_setup_recovery import snapshot
from okto_nexus.application.terminal_connection import ConnectionError, RemoteTerminalConnection
from okto_nexus.application.terminal_preset import TerminalPreset
from okto_nexus.adapters.outbound.service_manager.context import atomic_json, read_json

terminal = test_terminal_connect.terminal
checking = test_terminal_connect.checking
local_setup = test_terminal_connect.local_setup
onboarding = test_remote_project_policy.onboarding


def connected(t):
    review = t.flow.review(t.selection)
    t.flow.apply(review, approval=review['review_revision'])
    return deepcopy(t.saved[-1])


@pytest.mark.parametrize('lost', ['setup:test', 'setup:finish'])
def test_local_update_recovers_original_test_and_finish_without_repeating_effects(terminal, monkeypatch, lost):
    t, saved = terminal, []
    connection = connected(t)
    revision_two(monkeypatch)
    flow = TerminalPreset(t.call, lambda value: saved.append(deepcopy(value)), connection)
    before = snapshot(t.deps)
    ordinary = t.flow.apply(deepcopy(connection))
    assert ordinary['configuration']['project_preset']['revision'] == 1
    assert snapshot(t.deps) == before and len(t.turns) == 1
    review = flow.review()
    assert snapshot(t.deps) == before and len(t.turns) == 1
    with pytest.raises(ConnectionError, match='Approve'):
        flow.apply(review, approval='wrong')
    assert len(t.turns) == 1
    t.fault.after = lost
    with pytest.raises(ConnectionError, match='Injected'):
        flow.apply(review, approval=review['review_revision'])
    if lost == 'setup:finish':
        t.app.state.connection_tests.tests.clear()
    recovered = flow.apply(deepcopy(saved[-1]))
    assert recovered['state'] == 'preset_applied' and recovered['current_origin']['revision'] == 2
    assert len(t.turns) == 2 and len(t.probes) == 1
    assert len(snapshot(t.deps)['runtime_execution_grants']) == 2
    assert recovered['binding_id'] == connection['result']['binding']['binding_id']
    stable = snapshot(t.deps)
    flow.apply(deepcopy(saved[-1]))
    assert flow.review()['state'] == 'up_to_date'
    assert snapshot(t.deps) == stable and len(t.turns) == 2


def test_changed_review_is_refused_before_any_test(terminal, monkeypatch):
    t = terminal
    connection = connected(t)
    revision_two(monkeypatch)
    flow = TerminalPreset(t.call, lambda _: None, connection)
    review = flow.review()
    review['request']['configuration']['session_policy'] = 'shared'
    before = snapshot(t.deps)
    with pytest.raises(ConnectionError) as refused:
        flow.apply(review, approval=review['review_revision'])
    assert refused.value.code == 'REVIEW_CHANGED'
    assert snapshot(t.deps) == before and len(t.turns) == 1


def test_confirmed_server_refusal_can_be_reviewed_again_without_replaying_test(terminal, monkeypatch):
    t, saved = terminal, []
    connection = connected(t)
    revision_two(monkeypatch)
    flow = TerminalPreset(t.call, lambda value: saved.append(deepcopy(value)), connection)
    review = flow.review()
    with t.deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET role='Changed after review' WHERE agent_id='subject'")
    before = snapshot(t.deps)
    with pytest.raises(ConnectionError) as rejected:
        flow.apply(review, approval=review['review_revision'])
    assert rejected.value.code == 'CONFLICT' and saved[-1]['state'] == 'refused'
    assert len(t.turns) == 1 and snapshot(t.deps) == before
    with pytest.raises(ConnectionError, match='refresh'):
        flow.apply(saved[-1])
    fresh = flow.review()
    assert fresh['review_revision'] != review['review_revision']
    assert len(t.turns) == 1 and snapshot(t.deps) == before
    assert flow.apply(fresh, approval=fresh['review_revision'])['state'] == 'preset_applied'
    assert len(t.turns) == 2


def test_failed_test_requires_confirmed_cleanup_before_a_fresh_review(terminal, monkeypatch):
    t, saved = terminal, []
    connection = connected(t)
    revision_two(monkeypatch)
    async def failed_test(entry, request, candidate):
        t.turns.append(request['client_intent_id'])
        entry.update(status='failed', stage='Synthetic provider failure')
    monkeypatch.setattr(t.app.state.connection_tests, 'run', failed_test)
    flow = TerminalPreset(t.call, lambda value: saved.append(deepcopy(value)), connection)
    review = flow.review()
    result = flow.apply(review, approval=review['review_revision'])
    assert result['state'] == 'test_failed' and not result['test']['retryable_failure']
    assert saved[-1]['state'] == 'test_submitted' and len(t.turns) == 2
    # The Server later confirms closure of the same failed test, without rerun.
    entry = next(value for value in t.app.state.connection_tests.tests.values()
        if value['test_id'] == review['request']['client_intent_id'])
    entry['cleanup_confirmed'] = True
    result = flow.apply(deepcopy(saved[-1]))
    assert result['test']['retryable_failure'] is True and saved[-1]['state'] == 'refused'
    assert len(t.turns) == 2 and len(snapshot(t.deps)['runtime_execution_grants']) == 1


def test_cli_keeps_original_project_and_pending_update_checkpoint(terminal, monkeypatch, tmp_path, capsys):
    from okto_nexus.adapters.inbound.cli import preset
    t = terminal
    connection = connected(t)
    revision_two(monkeypatch)
    home = tmp_path / 'operator-home'
    path = home / 'terminal/profiles/project.json'
    path.parent.mkdir(parents=True)
    atomic_json(path, connection)
    starts = []
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=8202),
        inspect=lambda: {'state': 'ready'},
        ensure_running=lambda **kw: starts.append(True) or {'state': 'ready'})
    monkeypatch.setattr(preset, 'resolve_local_service', lambda *a, **kw: service)
    monkeypatch.setattr(preset, 'LocalOperatorHTTP', lambda **kw: t.call)
    args = ['--home', str(home), '--profile', 'project', '--json']
    assert preset.run_preset([*args, '--plan']) == 0
    review = json.loads(capsys.readouterr().out)
    assert review['state'] == 'review' and starts == [] and len(t.turns) == 1
    t.fault.after = 'setup:finish'
    assert preset.run_preset([*args, '--approve', review['review_revision']]) == 3
    assert json.loads(capsys.readouterr().out)['state'] == 'unconfirmed'
    stored = read_json(path)
    assert stored['request'] == connection['request'] and stored['result'] == connection['result']
    assert stored['preset_evolution']['state'] == 'finish'
    assert preset.run_preset([*args, '--refresh']) == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'UPDATE_PENDING'
    t.app.state.connection_tests.tests.clear()
    assert preset.run_preset(args) == 0
    assert json.loads(capsys.readouterr().out)['state'] == 'preset_applied'
    assert preset.run_preset([*args, '--plan']) == 0
    assert json.loads(capsys.readouterr().out)['state'] == 'up_to_date'
    assert read_json(path)['selection'] == connection['selection']
    assert len(t.turns) == 2 and len(snapshot(t.deps)['runtime_execution_grants']) == 2


@pytest.mark.parametrize('answer', ['decline', 'eof'])
def test_cli_decline_and_eof_leave_review_unapproved(terminal, monkeypatch, tmp_path, capsys, answer):
    from okto_nexus.adapters.inbound.cli import preset
    t = terminal
    connection = connected(t)
    revision_two(monkeypatch)
    home = tmp_path / 'operator-home'
    path = home / 'terminal/profiles/project.json'
    path.parent.mkdir(parents=True)
    atomic_json(path, connection)
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=8202),
        inspect=lambda: {'state': 'ready'}, ensure_running=lambda **kw: pytest.fail('Review started service'))
    monkeypatch.setattr(preset, 'resolve_local_service', lambda *a, **kw: service)
    monkeypatch.setattr(preset, 'LocalOperatorHTTP', lambda **kw: t.call)
    monkeypatch.setattr(preset.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    def respond(_):
        if answer == 'eof':
            raise EOFError()
        return 'n'
    monkeypatch.setattr('builtins.input', respond)
    before = snapshot(t.deps)
    assert preset.run_preset(['--home', str(home), '--profile', 'project']) == 0
    assert read_json(path)['preset_evolution']['state'] == 'review'
    assert snapshot(t.deps) == before and len(t.turns) == 1
    output = capsys.readouterr().out
    assert 'Agent: subject' in output and 'Revoke grant:' in output and 'New grant actions:' in output


def test_remote_connector_update_uses_human_authority_without_local_fallback_or_host_effects(onboarding, monkeypatch, tmp_path, capsys):
    from okto_nexus.adapters.inbound.cli import preset
    from okto_nexus.adapters.outbound import operator_client
    deps, client, headers, _ = onboarding
    proposal, request, approval = test_remote_project_policy.pending(onboarding)
    assert test_remote_project_policy.decide_binding(client, headers, approval).status_code == 200
    assert test_remote_project_policy.apply(client, headers, request).status_code == 200
    client.app.state.operator_auth.configure(**remote_helpers.ACCOUNT, local=True)
    vault, bridge = remote_helpers.MemoryVault(), remote_helpers.HTTPBridge(client)
    monkeypatch.setattr(operator_client, 'open_backend', lambda: vault)
    monkeypatch.setattr(operator_client, 'build_opener', lambda *a: bridge)
    operator = operator_client.OperatorProfile(tmp_path / 'human-client', 'remote')
    operator.login(remote_helpers.ORIGIN, **remote_helpers.ACCOUNT)
    saved = []
    flow = RemoteTerminalConnection(operator.client(), lambda value: saved.append(value))
    flow.review(dict(agent='subject', binding_id=proposal['binding_id'], project='local-shortcut',
        operator_profile='remote', client=None, workspace_id=None, candidate_ref=None))
    path = operator.home / 'terminal/profiles/project.json'
    path.parent.mkdir(parents=True)
    atomic_json(path, saved[-1])
    revision_two(monkeypatch)
    monkeypatch.setattr(preset, 'resolve_local_service', lambda *a: pytest.fail('Remote update resolved a local Server'))
    args = ['--home', str(operator.home), '--profile', 'project', '--json']
    bridge.calls.clear()
    before, secrets = snapshot(deps), deepcopy(vault.values)
    assert preset.run_preset([*args, '--plan']) == 0
    review = json.loads(capsys.readouterr().out)
    assert review['preset_review']['local_test_required'] is False
    assert snapshot(deps) == before and all(call.method == 'GET' for call in bridge.calls)
    bridge.after = '/connections/setup:finish'
    assert preset.run_preset([*args, '--approve', review['review_revision']]) == 3
    assert json.loads(capsys.readouterr().out)['state'] == 'unconfirmed'
    assert preset.run_preset(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'preset_applied' and result['current_origin']['revision'] == 2
    assert result['binding_id'] == proposal['binding_id']
    assert len(snapshot(deps)['runtime_execution_grants']) == len(before['runtime_execution_grants']) + 1
    assert vault.values == secrets
    assert all(secret not in path.read_text(encoding='utf-8') and secret not in json.dumps(result) for secret in secrets.values())
    assert not any(call.full_url.endswith(('setup:test', 'installations:check', '/runtime/operations')) for call in bridge.calls)
    assert sum(call.full_url.endswith('setup:finish') for call in bridge.calls) == 1
    assert not (operator.home / 'nexus.db').exists()
