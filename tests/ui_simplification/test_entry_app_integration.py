"""Production assembly, operator authorization and additive read compatibility."""
from fastapi.testclient import TestClient

from .test_fixtures import fixtures


def test_production_app_exposes_entries_without_manual_route_install(tmp_path):
    with fixtures.scenario(tmp_path/'production') as s:
        client = TestClient(s.app)  # scenario already owns the lifespan/WSS
        try:
            headers = {'Authorization': 'Bearer '+s.app.state.test_agent_keys['operator']}
            response = client.get('/api/v1/home/entries?quick=all', headers=headers)
            assert response.status_code == 200, response.text
            assert response.headers['cache-control'] == 'no-store'
            value = response.json()['data']
            assert value['version'] == 1 and value['partition'] == 'groups'
            assert value['items'] and value['server_id'] == s.connections[0].server_id
            legacy = client.get('/api/v1/home/overview', headers=headers)
            assert legacy.status_code == 200
            assert {'work', 'results', 'agents', 'attention', 'server_attention'} <= legacy.json()['data'].keys()
            assert client.post('/api/v1/home/entries', json={}, headers=headers).status_code == 405
            assert client.get('/api/v1/home/entries?unknown=1', headers=headers).status_code == 422
            assert client.get('/api/v1/home/entries?limit=1&limit=2', headers=headers).status_code == 422
        finally:
            client.close()


def test_agent_is_denied_before_any_entry_source_query(tmp_path):
    with fixtures.scenario(tmp_path/'denied') as s:
        class Tripwire:
            def read(self, *args, **kwargs):
                raise AssertionError('unauthorized source query')

            def external(self, *args, **kwargs):
                raise AssertionError('unauthorized observation query')

        s.app.state.home_entries.queries = Tripwire()
        client = TestClient(s.app)
        try:
            response = client.get('/api/v1/home/entries', headers={
                'Authorization': 'Bearer '+s.app.state.test_agent_keys['other']})
            assert response.status_code == 403, response.text
            assert response.headers['cache-control'] == 'no-store'
            assert 'items' not in response.json().get('data', {})
        finally:
            client.close()
