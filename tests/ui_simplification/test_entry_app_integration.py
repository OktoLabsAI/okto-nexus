"""Production assembly, operator authorization and additive read compatibility."""
from fastapi.testclient import TestClient
import pytest

from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError

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


def test_entries_cursor_is_bound_to_authenticated_human_without_exposing_identity(tmp_path):
    with fixtures.scenario(tmp_path/'human-cursor') as s:
        service=s.app.state.home_entries
        context=RuntimeRequestContext(None, 'operator_session', trusted_local_operator=True)
        first=service.read(context=context,principal='human-a',limit=1,filters={'quick':'all'})
        assert first['has_more'] and first['next_cursor']
        assert 'human-a' not in first['next_cursor']
        with pytest.raises(OktoNexusError) as error:
            service.read(context=context,principal='human-b',limit=1,filters={'quick':'all'},cursor=first['next_cursor'])
        assert error.value.code == 'CONFLICT'
        with pytest.raises(OktoNexusError) as error:
            service.read(context=context,limit=1,filters={'quick':'all'})
        assert error.value.code == 'PERMISSION_DENIED'


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
