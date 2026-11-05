"""Dashboard reads the terminal preset and edits the same canonical identity."""
from copy import deepcopy
import json

import pytest

import test_terminal_identity
from test_connection_setup_recovery import snapshot
from okto_nexus.application import project_preset

terminal = test_terminal_identity.terminal
checking = test_terminal_identity.checking
local_setup = test_terminal_identity.local_setup
agents = test_terminal_identity.agents


@pytest.mark.parametrize('prefix', ['/v1', '/api/v1/runtime-management'])
def test_project_recommendation_is_the_terminal_contract_and_applies_nothing(local_setup, prefix):
    deps, _, client, headers, *_ = local_setup
    before = agents(deps), snapshot(deps)
    response = client.get(prefix + '/connections/project-preset', headers=headers['operator'])
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    value = response.json()
    assert value['origin'] == project_preset.ORIGIN
    assert value['identity'] == project_preset.identity_defaults()
    assert value['effects'] == project_preset.effects()
    for adapter in project_preset.CLIENTS.values():
        config = project_preset.configuration(adapter_id=adapter, project='project', label='Project')
        assert value['configuration'] == {field: config[field] for field in value['configuration']}
    assert (agents(deps), snapshot(deps)) == before


@pytest.mark.parametrize('prefix', ['/v1', '/api/v1/runtime-management'])
def test_agent_key_cannot_read_operator_recommendation(local_setup, prefix):
    deps, _, client, headers, *_ = local_setup
    before = agents(deps), snapshot(deps)
    response = client.get(prefix + '/connections/project-preset', headers=headers['subject'])
    assert response.status_code == 403, response.text
    assert (agents(deps), snapshot(deps)) == before


def test_dashboard_personalization_and_terminal_reopen_preserve_identity_history_and_grants(terminal):
    t = terminal
    document = test_terminal_identity.review(t)
    result = t.flow.apply(document, approval=document['review_revision'])
    agent_id = 'project-assistant'
    path = '/api/v1/agents/' + agent_id
    setup_path = '/api/v1/runtime-management/connections/setup/' + agent_id
    initial = t.call('GET', setup_path)
    connection = initial['connections'][0]
    setup_path += '?binding_id=' + connection['binding_id']
    before_setup = t.call('GET', setup_path)
    assert before_setup['project_preset'] == project_preset.ORIGIN
    assert before_setup['runtime_policy']['session_policy'] == 'per_sender'
    t.call('POST', '/api/v1/steering/messages', dict(workspace=connection['workspace_id'],
        to_agent_id=agent_id, subject='Existing project history', body='Retain this project note.'))
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        history = [tuple(row) for row in uow.connection.execute('SELECT * FROM messages')]
    assert history
    before_agents, before_authority = agents(t.deps), snapshot(t.deps)
    assert agent_id in {agent['agent_id'] for agent in t.call('GET', '/api/v1/agents')['data']['items']}
    public = t.call('GET', path)['data']
    edited = deepcopy(public['metadata']) | {'display_name': 'Project reviewer', 'custom': {'code': '007', 'enabled': False}}
    t.call('PATCH', path, dict(role='Review specialist', capabilities=[], metadata=edited))
    changed = t.call('GET', path)['data']
    assert changed['agent_id'] == agent_id and changed['metadata'] == edited
    assert changed['role'] == 'Review specialist'
    after_agents = agents(t.deps)
    assert set(after_agents) == set(before_agents)
    for field in ('api_key_hash', 'permissions', 'created_at', 'is_active'):
        assert after_agents[agent_id][field] == before_agents[agent_id][field]
    assert json.loads(after_agents[agent_id]['metadata']) == edited
    assert t.call('GET', setup_path) == before_setup
    assert t.flow.apply(deepcopy(t.saved[-1])) == result
    assert snapshot(t.deps) == before_authority
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        assert [tuple(row) for row in uow.connection.execute('SELECT * FROM messages')] == history
    assert len(t.probes) == len(t.turns) == 1
