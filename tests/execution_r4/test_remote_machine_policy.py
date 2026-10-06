import json

import pytest
from nexus_connector_core import InstallationCandidate
from nexus_connector_core.discovery import fingerprint

from okto_nexus.adapters.outbound.execution.core_inventory import local_inventory_snapshot
from test_binding_operator import onboarding, prepare_delegated, decide_binding, connection_preferences


def second_machine(deps, client, headers, prepare, tmp_path):
    response = client.post('/v1/connections/executors:register', headers=headers['subject'], json=dict(
        client_intent_id='machine-y', connector_id='connector-y', label='Remote host', control_capabilities=[]))
    assert response.status_code == 201, response.text
    machine = response.json()
    executor = machine['executor_id']
    ticket = {'Authorization': 'Bearer ' + machine['bootstrap_ticket']['ticket']}
    binary = tmp_path / 'remote-only' / 'codex.exe'
    candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
    inventory = local_inventory_snapshot([candidate], server_id=machine['server_id'], executor_id=executor,
                                         producer_instance_id='peer-y', publication_sequence=1)
    assert client.put(f'/v1/runtime/executors/{executor}/inventory', headers=ticket, json=inventory).status_code == 200
    realized = client.post(f'/v1/runtime/executors/{executor}/realizations', headers=ticket, json=dict(
        client_intent_id='realization-y', agent_id='subject', local_realization_ref='root_yyyyyyyyyyyyyyyy',
        realization_revision=1, workspace_id=prepare['workspace_id'], workspace_label='Project',
        adapter_id=prepare['adapter_id'], candidate_ref=inventory['evidence'][0]['candidate_ref'],
        inventory_revision=inventory['inventory_revision'], local_root_proof_digest='sha256:'+'d'*64,
        configuration_digest='sha256:'+'e'*64, local_consent_id='consent-y'))
    assert realized.status_code == 201, realized.text
    return {**prepare, 'client_intent_id':'prepare-y', 'executor_id':executor,
        'realization_ref':realized.json()['realization_ref'], 'candidate_ref':inventory['evidence'][0]['candidate_ref'],
        'inventory_revision':inventory['inventory_revision']}


@pytest.mark.parametrize('policy', ['manual', 'deny', 'auto_replace'])
def test_different_machine_same_agent_and_same_host_label(onboarding, tmp_path, policy):
    deps, client, headers, prepare = onboarding
    prepare['connection_configuration'] = connection_preferences(prepare)
    _, first_apply, first_approval = prepare_delegated(client, headers, prepare)
    assert decide_binding(client, headers, first_approval).status_code == 200
    first = client.post('/v1/connections/bindings:apply', headers=headers['subject'], json=first_apply).json()
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_execution_grants SET used_executions=7')
        original = dict(uow.connection.execute('SELECT * FROM runtime_execution_grants').fetchone())
    other = second_machine(deps, client, headers, prepare, tmp_path)
    deps.config.remote_machine_policy = policy
    if policy == 'auto_replace':
        other['connection_configuration']['authorization'] = {'minutes':1440, 'actions':1000}
    response = client.post('/v1/connections/bindings:prepare', headers=headers['subject'], json=other)
    if policy == 'deny':
        assert response.status_code == 403, response.text
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT COUNT(*) FROM approvals').fetchone()[0] == 1
            assert uow.connection.execute('SELECT enabled FROM agent_endpoints').fetchone()[0] == 1
        return
    assert response.status_code == 200, response.text
    proposed = response.json()
    assert first['executor_id'] in proposed['diff']['summary']
    assert other['executor_id'] in proposed['diff']['summary']
    apply = dict(client_intent_id='apply-y', proposal_id=proposed['proposal_id'],
                 proposal_revision=1, approved_diff_hash=proposed['diff']['approved_diff_hash'])
    if policy == 'manual':
        approval = next(a for a in proposed['required_approvals'] if a.startswith('apr_'))
        assert approval != first_approval
        apply['operator_proof_ref'] = first_approval
        assert client.post('/v1/connections/bindings:apply', headers=headers['subject'], json=apply).status_code == 403
        apply['operator_proof_ref'] = approval
        assert decide_binding(client, headers, approval).status_code == 200
    else:
        assert not any(a.startswith('apr_') for a in proposed['required_approvals'])
    client._transport.raise_server_exceptions = True
    result = client.post('/v1/connections/bindings:apply', headers=headers['subject'], json=apply)
    assert result.status_code == 200, result.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        old = uow.connection.execute('SELECT enabled,activation_state FROM agent_endpoints WHERE endpoint_id=?', (first['endpoint_id'],)).fetchone()
        assert tuple(old) == (0, 'revoked')
        assert uow.connection.execute('SELECT revoked_at FROM runtime_execution_grants WHERE grant_id=?', (original['grant_id'],)).fetchone()[0]
        current = uow.connection.execute('SELECT * FROM runtime_execution_grants WHERE revoked_at IS NULL').fetchone()
        assert current['endpoint_id'] == result.json()['endpoint_id']
        if policy == 'auto_replace':
            assert current['expires_at'] == original['expires_at']
            assert current['max_executions'] == 20 and current['used_executions'] == 7
    previous = client.get('/v1/connections/bindings/'+first['binding_id'], headers=headers['subject'])
    assert previous.json()['state'] == 'REVOKED'
    status = client.get('/v1/connections/status', headers=headers['subject'])
    assert status.status_code == 200, status.text
    connections = {r['binding_id']:r for r in status.json()['connections']}
    assert connections[first['binding_id']]['status'] == 'REVOKED'
    assert connections[result.json()['binding_id']]['status'] == 'OFFLINE'
    assert connections[first['binding_id']]['machine_id'] != connections[result.json()['binding_id']]['machine_id']
    assert client.get('/v1/connections/status', headers=headers['other']).json()['connections'] == []


@pytest.mark.parametrize('change', ['policy', 'budget', 'preferences'])
def test_automatic_replacement_revalidates_authority_and_never_revokes_on_failure(onboarding, tmp_path, change):
    deps, client, headers, prepare = onboarding
    prepare['connection_configuration'] = connection_preferences(prepare)
    _, first_apply, approval = prepare_delegated(client, headers, prepare)
    assert decide_binding(client, headers, approval).status_code == 200
    first = client.post('/v1/connections/bindings:apply', headers=headers['subject'], json=first_apply).json()
    other = second_machine(deps, client, headers, prepare, tmp_path)
    deps.config.remote_machine_policy = 'auto_replace'
    if change == 'preferences':
        other['connection_configuration']['tool_access'] = 'always_allow'
    response = client.post('/v1/connections/bindings:prepare', headers=headers['subject'], json=other)
    if change == 'preferences':
        assert response.status_code == 403
    else:
        assert response.status_code == 200, response.text
        p = response.json()
        if change == 'policy':
            deps.config.remote_machine_policy = 'deny'
        else:
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute('UPDATE runtime_execution_grants SET used_executions=max_executions')
        response = client.post('/v1/connections/bindings:apply', headers=headers['subject'], json=dict(
            client_intent_id='apply-y', proposal_id=p['proposal_id'], proposal_revision=1,
            approved_diff_hash=p['diff']['approved_diff_hash']))
        assert response.status_code in (403,409), response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_bindings').fetchone()[0] == 1
        assert uow.connection.execute('SELECT enabled FROM agent_endpoints WHERE endpoint_id=?', (first['endpoint_id'],)).fetchone()[0] == 1
