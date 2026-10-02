"""Eligibility combines executor evidence and authority without creating effects."""
from dataclasses import replace

import pytest
import nexus_connector_core.availability as availability
import test_binding_operator
from test_binding_operator import onboarding, prepare_operator
from okto_nexus.domain.base import iso_plus


@pytest.fixture
def options_host(request, monkeypatch):
    original = test_binding_operator.local_inventory_snapshot
    def snapshot(candidates, **kwargs):
        # Synthetic executor assessment only. No native-provider qualification
        # or independent-host acceptance is claimed by this unit fixture.
        with monkeypatch.context() as patch:
            patch.setattr(availability, 'qualified_build', lambda *a, **k: getattr(request, 'param', 'ready') == 'ready')
            patch.setattr(availability, 'containment_preflight', lambda **k: {'job_objects': 'ok'})
            return original([replace(c, version='0.159.0', architecture='x86_64') for c in candidates], **kwargs)
    monkeypatch.setattr(test_binding_operator, 'local_inventory_snapshot', snapshot)
    deps, client, headers, prepare = request.getfixturevalue('onboarding')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET control_state='CONTROL_READY' WHERE executor_id=?",
                               (prepare['executor_id'],))
    return deps, client, headers, prepare


def option(host, actor='subject', workspace=True):
    _, client, headers, scope = host
    query = {'executor_id': scope['executor_id']}
    if workspace:
        query['workspace_id'] = scope['workspace_id']
    response = client.get('/v1/agents/subject/runtime-options', params=query, headers=headers[actor])
    assert response.status_code == 200, response.text
    assert response.headers['Cache-Control'] == 'no-store'
    result = response.json()
    selected = next(row for row in result['options'] if row['candidate_ref'] == scope['candidate_ref'])
    return result, selected


def bind(host):
    _, client, headers, prepare = host
    _, body = prepare_operator(client, headers, prepare)
    response = client.post('/v1/connections/bindings:apply', json=body, headers=headers['operator'])
    assert response.status_code == 200, response.text
    return response.json()


def grant(host, binding):
    deps, client, headers, _ = host
    response = client.post('/api/v1/harness/grants', headers=headers['operator'], json={
        'actor_agent_id': 'subject', 'endpoint_id': binding['endpoint_id'],
        'actions': ['open'], 'max_executions': 1,
        'expires_at': iso_plus(deps.clock.now_iso(), 600),
    })
    assert response.status_code == 200, response.text


def test_workspace_binding_and_grant_each_gate_a_different_action(options_host, monkeypatch):
    _, first = option(options_host, workspace=False)
    assert first['technical_state'] == 'READY_FOR_RUNTIME'
    assert first['can_prepare'] and not first['can_bind'] and not first['can_start']
    assert 'WORKSPACE_REQUIRED' in first['policy_reasons']
    _, pending = option(options_host, actor='operator')
    assert pending['can_bind'] and not pending['can_start']
    _, subject = option(options_host)
    assert not subject['can_bind'] and 'OPERATOR_APPROVAL_REQUIRED' in subject['policy_reasons']
    binding = bind(options_host)
    _, unauthorized = option(options_host)
    assert not unauthorized['can_start'] and 'AUTHORIZATION_REQUIRED' in unauthorized['policy_reasons']
    grant(options_host, binding)
    # A Server read must use the published executor assessment, not probe or
    # reassess a provider under the Server's own platform/containment state.
    monkeypatch.setattr(availability, 'evaluate_runtime_availability', lambda *a, **k: pytest.fail('Server reassessed provider'))
    monkeypatch.setattr(availability, 'containment_preflight', lambda **k: pytest.fail('Server checked native containment'))
    _, authorized = option(options_host)
    assert authorized['can_start'], authorized
    _, operator = option(options_host, actor='operator')
    assert not operator['can_start']
    assert 'SUBJECT_IDENTITY_REQUIRED' in operator['policy_reasons']
    deps = options_host[0]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ('execution_operations', 'execution_dispatch_outbox', 'execution_sessions'):
            assert uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants').fetchone()[0] == 0


@pytest.mark.parametrize('options_host', ['unqualified'], indirect=True)
def test_unqualified_inventory_can_be_prepared_but_never_started(options_host):
    binding = bind(options_host)
    grant(options_host, binding)
    result, row = option(options_host)
    assert row['technical_state'] == 'UNQUALIFIED_BUILD'
    assert row['can_prepare'] and not row['can_start']
    assert 'TECHNICAL_NOT_READY' in row['policy_reasons']
    technical = next(item for item in result['availability']['availability']
                     if item['candidate_ref'] == row['candidate_ref'])
    assert row['technical_reasons'] == technical['reasons']


@pytest.mark.parametrize(('change', 'reason'), [
    ('offline', 'EXECUTOR_OFFLINE'), ('stale', 'INVENTORY_STALE'),
    ('feature', 'FEATURE_DISABLED'), ('method', 'METHOD_DISABLED'),
    ('endpoint', 'BINDING_DISABLED'), ('profile', 'BINDING_DISABLED'),
    ('grant', 'AUTHORIZATION_REQUIRED'), ('workspace', 'BINDING_REQUIRED'),
])
def test_current_policy_or_evidence_changes_disable_start(options_host, change, reason):
    deps, client, _, scope = options_host
    binding = bind(options_host)
    grant(options_host, binding)
    before, row = option(options_host)
    assert row['can_start'], row
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        if change == 'offline':
            conn.execute("UPDATE execution_executors SET control_state='DISCONNECTED' WHERE executor_id=?", (scope['executor_id'],))
        elif change == 'stale':
            client.app.state.inventory_fresh_publications.clear()
        elif change == 'feature':
            deps.config = replace(deps.config, feature_harness_integrations=False)
        elif change == 'method':
            conn.execute("INSERT INTO agent_connection_methods(agent_id,method,enabled) VALUES ('subject','codex_app_server',0)")
        elif change == 'endpoint':
            conn.execute('UPDATE agent_endpoints SET enabled=0 WHERE endpoint_id=?', (binding['endpoint_id'],))
        elif change == 'profile':
            conn.execute('UPDATE runtime_profiles SET enabled=0')
        elif change == 'grant':
            conn.execute("UPDATE runtime_execution_grants SET expires_at='2000-01-01T00:00:00Z'")
        else:
            scope['workspace_id'] = 'different-workspace'
    after, row = option(options_host)
    assert not row['can_start'] and reason in row['policy_reasons'], row
    assert after['availability'] == before['availability']


@pytest.mark.parametrize('query', [
    'executor_id=one&executor_id=two', 'executor_id=one&workspace_id=x&workspace_id=y',
    'executor_id=one&workspace_id=', 'executor_id=one&unexpected=true',
])
def test_options_reject_ambiguous_or_invalid_query(onboarding, query):
    _, client, headers, _ = onboarding
    response = client.get('/v1/agents/subject/runtime-options?' + query, headers=headers['subject'])
    assert response.status_code == 422, response.text
