"""Inventory read scope is revalidated without changing executor-owned facts."""

from dataclasses import replace

import pytest

from test_binding_operator import onboarding
from test_binding_views import bound
from okto_nexus.application.executor_inventory_views import read_executor_inventory
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError


def test_operator_can_read_subject_options_without_changing_technical_facts(bound):
    deps, client, headers, binding = bound
    path = '/v1/agents/subject/runtime-options'
    query = {'executor_id': binding['executor_id']}
    subject = client.get(path, params=query, headers=headers['subject'])
    operator = client.get(path, params=query, headers=headers['operator'])
    assert subject.status_code == operator.status_code == 200
    assert subject.json() == operator.json()
    assert operator.headers['Cache-Control'] == 'no-store'
    denied = client.get(path, params=query, headers=headers['other'])
    assert denied.status_code == 403
    assert denied.json()['error']['code'] == 'SCOPE_MISMATCH'
    assert client.get('/v1/agents/missing/runtime-options', params=query,
                      headers=headers['operator']).status_code == 404
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0


def test_inventory_authorizes_binding_subject_separately_from_registrar(bound):
    deps, client, headers, binding = bound
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_executors SET registered_by_agent_id='operator' WHERE executor_id=?",
                               (binding['executor_id'],))
    path = '/v1/runtime/executors/' + binding['executor_id'] + '/inventory'
    subject = client.get(path, headers=headers['subject'])
    assert subject.status_code == 200, subject.text
    assert client.get(path, headers=headers['operator']).json() == subject.json()
    denied = client.get(path, headers=headers['other'])
    assert denied.status_code == 404
    assert denied.headers['Cache-Control'] == 'no-store'
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE agent_endpoints SET enabled=0 WHERE endpoint_id=?', (binding['endpoint_id'],))
    assert client.get(path, headers=headers['subject']).status_code == 404
    # Recovery inspection is available to the operator when execution is disabled.
    deps.config = replace(deps.config, feature_harness_integrations=False)
    assert client.get(path, headers=headers['operator']).status_code == 200


def test_inventory_revalidates_operator_credential_inside_transaction(bound):
    deps, client, headers, binding = bound
    with deps.connection_factory.unit_of_work() as uow:
        old = uow.connection.execute("SELECT api_key_hash FROM agents WHERE agent_id='operator'").fetchone()[0]
        client.app.state.auth.issue_key(uow, agent_id='operator')
    with pytest.raises(OktoNexusError) as refused:
        read_executor_inventory(deps.connection_factory, server_id=binding['server_id'],
            executor_id=binding['executor_id'], agent_id='subject',
            fresh_publications=client.app.state.inventory_fresh_publications,
            context=RuntimeRequestContext('operator', 'agent_key', credential_binding=old),
            access=build_execution_access(deps))
    assert refused.value.code == 'PERMISSION_DENIED'
