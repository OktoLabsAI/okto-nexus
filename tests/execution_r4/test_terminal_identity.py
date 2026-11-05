"""A reviewed project identity is created exactly once by canonical Finish."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

import test_terminal_connect
from test_connection_setup import finish
from test_connection_setup_recovery import snapshot
from okto_nexus.adapters.inbound.cli import connect
from okto_nexus.application.connection_setup import load_setup
from okto_nexus.application.execution_local_realizations import directory_identity
from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError

terminal = test_terminal_connect.terminal
checking = test_terminal_connect.checking
local_setup = test_terminal_connect.local_setup


def agents(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        # Authenticated reads update presence; compare identity/authority state.
        return {row['agent_id']: {key: row[key] for key in row.keys() if key != 'last_seen_at'}
                for row in uow.connection.execute('SELECT * FROM agents')}


def review(t):
    return t.flow.review(dict(t.selection, agent='project-assistant', create_agent=True, display_name=None))


@pytest.mark.parametrize('lost_finish', [False, True])
def test_finish_creates_one_reviewed_identity_and_recovery_never_rotates_its_key(terminal, monkeypatch, lost_finish):
    from okto_nexus.application.auth import AgentKeyAuthService
    from okto_nexus.application import runtime_policy

    t = terminal
    context = RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        defaults = runtime_policy.defaults(uow.connection)
    runtime_policy.save_policy(t.deps, context, changes=dict(expected_revision=defaults['revision'],
        runtime_enabled=defaults['runtime_enabled'], session_policy=defaults['session_policy'],
        broadcast_handoff_auto_claim=True))
    original = AgentKeyAuthService.issue_key
    issued = []
    def issue(auth, uow, *, agent_id):
        value = original(auth, uow, agent_id=agent_id)
        issued.append(value)
        return value
    monkeypatch.setattr(AgentKeyAuthService, 'issue_key', issue)
    before = agents(t.deps), snapshot(t.deps)
    document = review(t)
    assert document['identity_creation']['display_name'] == 'Codex — Project'
    assert document['request']['broadcast_handoff_auto_claim'] is False
    assert (agents(t.deps), snapshot(t.deps)) == before
    assert t.probes == t.turns == issued == []
    if lost_finish:
        t.fault.after = 'setup:finish'
        with pytest.raises(ConnectionError, match='Injected'):
            t.flow.apply(document, approval=document['review_revision'])
        t.app.state.connection_tests.tests.clear()
        document = deepcopy(t.saved[-1])
    result = t.flow.apply(document, approval=document['review_revision'])
    assert result['state'] == 'configured' and result['work_state'] == 'not_submitted'
    assert set(agents(t.deps)) == set(before[0]) | {'project-assistant'}
    row = agents(t.deps)['project-assistant']
    assert row['role'] == 'Project assistant'
    assert json.loads(row['metadata'])['display_name'] == 'Codex — Project'
    assert row['is_active'] and len(row['api_key_hash']) == 64
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        assert runtime_policy.defaults(uow.connection)['broadcast_handoff_auto_claim'] is True
        assert runtime_policy.effective(uow.connection, 'project-assistant')['broadcast_handoff_auto_claim'] is False
        grant = dict(uow.connection.execute('SELECT * FROM runtime_execution_grants').fetchone())
        assert 'execute_work' not in json.dumps(grant)
    permissions = json.loads(row['permissions'])
    assert permissions['messages'] == dict(send_direct=True, send_channel=True, send_broadcast=False)
    assert permissions['handoffs'] == dict(create=True, work=True, cancel=True)
    assert permissions['identity']['update_capabilities'] is False
    assert permissions['workspaces']['include_paths'] is False
    assert not any(permissions['experimental'].values())
    after = agents(t.deps), snapshot(t.deps)
    assert len(after[1]['runtime_execution_grants']) == len(after[1]['execution_bindings']) == 1
    assert document['result']['agent_created'] is True
    assert len(issued) == len(t.turns) == len(t.probes) == 1
    # The ordinary key authority initializes the identity; the managed setup
    # never exports that root key to the receipt, HTTP result or profile.
    assert issued[0] not in json.dumps([t.saved, result, document['result']])
    assert 'api_key' not in json.dumps([t.saved, result])
    assert t.flow.apply(deepcopy(t.saved[-1])) == result
    assert (agents(t.deps), snapshot(t.deps)) == after
    assert len(issued) == len(t.turns) == len(t.probes) == 1


def test_test_draft_has_no_identity_and_its_result_remains_readable_after_finish(terminal):
    t = terminal
    document = review(t)
    before = agents(t.deps), snapshot(t.deps)
    t.fault.after = 'setup:test'
    with pytest.raises(ConnectionError, match='Injected'):
        t.flow.apply(document, approval=document['review_revision'])
    assert len(t.turns) == 1
    assert (agents(t.deps), snapshot(t.deps)) == before
    resumed = deepcopy(t.saved[-1])
    assert t.flow.apply(resumed)['state'] == 'configured'
    assert t.flow.api('GET', '/connections/setup-tests/' + resumed['request']['client_intent_id'])['status'] == 'succeeded'
    with pytest.raises(ConnectionError, match='now exists'):
        t.flow.api('POST', '/connections/setup:test', resumed['request'])
    assert len(t.turns) == 1


@pytest.mark.parametrize('after_test', [False, True])
def test_colliding_identity_is_never_adopted_or_modified(terminal, after_test):
    t = terminal
    document = review(t)
    if after_test:
        t.fault.after = 'setup:test'
        with pytest.raises(ConnectionError):
            t.flow.apply(document, approval=document['review_revision'])
    created = t.call('POST', '/api/v1/agents', dict(agent_id='project-assistant', role='Existing owner'))
    assert created['data']['role'] == 'Existing owner'
    before = agents(t.deps), snapshot(t.deps)
    operation = 'finish' if after_test else 'test'
    with pytest.raises(ConnectionError, match='now exists'):
        t.flow.api('POST', '/connections/setup:' + operation, document['request'])
    assert (agents(t.deps), snapshot(t.deps)) == before
    assert len(t.turns) == int(after_test)


@pytest.mark.parametrize('operation', ['test', 'finish'])
def test_changed_defaults_require_new_review_before_effects(terminal, local_setup, monkeypatch, operation):
    from okto_nexus.application import project_preset

    t = terminal
    document = review(t)
    defaults = project_preset.identity_defaults()
    monkeypatch.setattr(project_preset, 'identity_defaults', lambda: defaults | {'defaults_hash': 'sha256:' + '0' * 64})
    before = agents(t.deps), snapshot(t.deps)
    if operation == 'test':
        with pytest.raises(ConnectionError, match='defaults changed'):
            t.flow.api('POST', '/connections/setup:test', document['request'])
    else:
        # Exercise the transaction's own check independently of the HTTP test
        # manager, which also revalidates the draft before accepting Finish.
        context = RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)
        with pytest.raises(OktoNexusError, match='defaults changed'):
            finish(local_setup, context, document['request'], verified=None)
    assert (agents(t.deps), snapshot(t.deps)) == before
    assert t.turns == t.probes == []


@pytest.mark.parametrize('mutation', ['permissions', 'blank_name', 'remote', 'existing_binding'])
def test_invalid_creation_draft_cannot_start_model_test(terminal, local_setup, mutation):
    t = terminal
    request = deepcopy(review(t)['request'])
    if mutation == 'permissions':
        request['agent_creation']['permissions'] = {'messages': {'send_broadcast': True}}
    elif mutation == 'blank_name':
        request['agent_creation']['display_name'] = '  '
    elif mutation == 'remote':
        request['configuration']['execution_location'] = 'remote'
    else:
        request['binding_id'] = 'existing-binding'
    before = agents(t.deps), snapshot(t.deps)
    response = local_setup[2].post('/api/v1/runtime-management/connections/setup:test',
                                   headers={'X-Nexus-UI': '1'}, json=request)
    assert response.status_code == 422, response.text
    assert (agents(t.deps), snapshot(t.deps)) == before
    assert t.turns == t.probes == []


def test_late_finish_failure_rolls_back_identity_key_and_every_setup_object(terminal, local_setup, monkeypatch):
    from okto_nexus.application import execution_binding_proposals

    t = terminal
    document = review(t)
    t.fault.after = 'setup:test'
    with pytest.raises(ConnectionError, match='Injected'):
        t.flow.apply(document, approval=document['review_revision'])
    before = agents(t.deps), snapshot(t.deps)
    context = RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True)
    def fail_after_workspace_and_identity(*args, **kwargs):
        # Nested setup operations share the outer transaction, not a separate
        # commit. This failure occurs after creating the identity/workspace.
        raise RuntimeError('injected late binding failure')
    monkeypatch.setattr(execution_binding_proposals, 'prepare_execution_binding', fail_after_workspace_and_identity)
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        workspaces_before = [tuple(row) for row in uow.connection.execute('SELECT * FROM workspaces')]
    with pytest.raises(RuntimeError, match='injected late'):
        finish(local_setup, context, document['request'], verified={
            'root': directory_identity(t.selection['project']),
            'home': directory_identity(document['request']['configuration']['provider_home'])
                    if document['request']['configuration']['provider_home'] else None})
    assert (agents(t.deps), snapshot(t.deps)) == before
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        assert [tuple(row) for row in uow.connection.execute('SELECT * FROM workspaces')] == workspaces_before


def test_draft_operator_authority_and_reserved_identity_checks(terminal, local_setup):
    t = terminal
    request = review(t)['request']
    client, headers = local_setup[2:4]
    before = agents(t.deps), snapshot(t.deps)
    for prefix in ('/v1', '/api/v1/runtime-management'):
        path = prefix + '/connections/setup/project-assistant?new_agent_draft=true'
        assert client.get(path, headers=headers['subject']).status_code == 403
        for operation in ('test', 'finish'):
            assert client.post(prefix + '/connections/setup:' + operation,
                               headers=headers['subject'], json=request).status_code == 403
        for reserved in ('operator', 'Operator', ' OPERATOR '):
            response = client.get(prefix + '/connections/setup/' + reserved,
                params={'new_agent_draft': 'true'}, headers=headers['operator'])
            assert response.status_code == 422
    assert (agents(t.deps), snapshot(t.deps)) == before
    assert t.turns == t.probes == []


def test_default_cli_review_is_stable_and_reconnect_preserves_identity_customizations(terminal, tmp_path, monkeypatch, capsys):
    t = terminal
    service = SimpleNamespace(adapter=SimpleNamespace(home=tmp_path / 'terminal-home', host='127.0.0.1', port=8202),
        inspect=lambda: {'state': 'ready'}, ensure_running=lambda **kwargs: {'state': 'ready'})
    monkeypatch.setattr(connect, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    args = ['--profile', 'default-project', '--project', t.selection['project'], '--json']
    before = agents(t.deps), snapshot(t.deps)
    assert connect.run_connect(args + ['--plan']) == 0
    document = json.loads(capsys.readouterr().out)
    assert document['selection']['create_agent'] is True
    assert document['identity_creation']['display_name'].startswith('Codex — ')
    assert (agents(t.deps), snapshot(t.deps)) == before
    assert connect.run_connect(args + ['--plan']) == 0
    assert json.loads(capsys.readouterr().out) == document
    # Reuse is a different choice until this proposed identity has committed.
    assert connect.run_connect(args + ['--plan', '--agent', document['selection']['agent']]) == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'PROFILE_CONFLICT'
    assert connect.run_connect(args + ['--approve', document['review_revision']]) == 0
    result = json.loads(capsys.readouterr().out)
    agent_id = result['agent_id']
    t.call('PATCH', '/api/v1/agents/' + agent_id, dict(role='Maintainer', metadata={'display_name': 'My helper'},
        permissions={'messages': {'send_direct': False}}))
    after = agents(t.deps), snapshot(t.deps)
    assert connect.run_connect(['--profile', 'default-project', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['agent_id'] == agent_id
    assert (agents(t.deps), snapshot(t.deps)) == after
    assert len(t.turns) == len(t.probes) == 1
    assert load_setup(t.deps, RuntimeRequestContext('operator', 'http_loopback', trusted_local_operator=True),
                      agent_id, result['binding_id'])['project_preset'] == {'id': 'project-generalist', 'revision': 1}
