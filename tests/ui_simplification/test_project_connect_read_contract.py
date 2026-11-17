"""UI035 reads canonical draft/catalog APIs without Test/Finish/provider calls."""
# ruff: noqa: F811 -- imported pytest scenario is injected by its fixture name
from fastapi.testclient import TestClient

from .test_fixtures import scenario as scenario


def counts(s):
    with s.factory.unit_of_work(write=False) as uow:
        return {table: uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                for table in ('agents', 'runtime_execution_grants', 'execution_sessions', 'execution_operations')}


def test_short_flow_read_contract_exposes_safe_directory_and_uncreated_identity_draft(scenario):
    s = scenario
    before = counts(s)
    headers = {'Authorization': 'Bearer '+s.app.state.test_agent_keys['operator'], 'x-nexus-ui': '1'}
    client = TestClient(s.app)
    try:
        response = client.get('/api/v1/runtime-management/connections/workspaces?limit=100', headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        page = response.json()
        assert any(item['workspace_id'] == 'ws' for item in page['items'])
        assert all(set(item) == {'workspace_id', 'display_name'} for item in page['items'])
        response = client.get('/api/v1/runtime-management/connections/setup/proposed_project_collaborator?new_agent_draft=true', headers=headers)
        assert response.status_code == 200, response.text
        draft = response.json()
        assert draft['baseline']['binding_revision'] is None
        assert draft['agent_creation_defaults']['defaults_hash'].startswith('sha256:')
        assert len(draft['native_decision_policy']['revision']) == 64
        assert draft['connections'] == []
        me = client.get('/api/v1/runtime-management/connections/me', headers=headers)
        assert me.status_code == 200
        response = client.get('/api/v1/runtime-management/connections/catalog?workspace_id=ws&limit=100', headers=headers)
        assert response.status_code == 200, response.text
        catalog = response.json()
        assert catalog['server_id'] == me.json()['server_id']
        assert catalog['requires_canonical_revalidation'] is True
        assert all(item['workspace_id'] == 'ws' and item['needs_revalidation'] is True for item in catalog['items'])
        assert counts(s) == before
        with s.factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT 1 FROM agents WHERE agent_id='proposed_project_collaborator'").fetchone() is None
        assert not s.app.state.connection_tests.tests
    finally:
        client.close()


def test_agent_credentials_cannot_turn_a_draft_reference_into_operator_creation_authority(scenario):
    s = scenario
    before = counts(s)
    client = TestClient(s.app)
    try:
        response = client.get('/api/v1/runtime-management/connections/setup/proposed_project_collaborator?new_agent_draft=true',
                              headers={'Authorization': 'Bearer '+s.app.state.test_agent_keys['subject'], 'x-nexus-ui': '1'})
        assert response.status_code == 403
        assert counts(s) == before
    finally:
        client.close()
