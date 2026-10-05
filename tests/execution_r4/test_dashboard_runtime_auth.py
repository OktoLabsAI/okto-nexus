"""Loopback UI authority is explicit; canonical agent transports stay keyed."""
import pytest
from test_local_realization import local_setup


def test_keyless_loopback_can_configure_local_but_not_use_agent_transport(local_setup):
    deps, app, client, _, body, *_ = local_setup
    app.state.local_open = True
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET api_key_hash=NULL WHERE agent_id='operator'")
    prefix = '/api/v1/runtime-management'
    response = client.get(prefix + '/agents/subject/executors')
    assert response.status_code == 200, response.text
    executor = next(item['executor_id'] for item in response.json()['items'] if item['kind'] == 'embedded')
    assert client.get('/v1/agents/subject/executors').status_code == 401
    assert client.post('/mcp', json={}).status_code == 401
    response = client.get(prefix + '/agents/subject/runtime-options', params={'executor_id': executor})
    assert response.status_code == 200, response.text
    assert response.json()['catalog']['runtimes']
    assert any(item['can_prepare'] for item in response.json()['options'])
    response = client.post(prefix + f'/runtime/executors/{executor}/realizations', json=body)
    assert response.status_code == 201, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT actor_agent_id FROM execution_local_realizations").fetchone()[0] == 'operator'
        assert uow.connection.execute("SELECT api_key_hash FROM agents WHERE agent_id='operator'").fetchone()[0] is None
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0] == 0


@pytest.mark.parametrize('headers,status', [
    ({'Authorization': 'Bearer invalid'}, 401),
    ({'x-api-key': 'invalid'}, 401),
    ({'Origin': 'https://untrusted.example'}, 403),
    ({'Host': 'rebound.example', 'Sec-Fetch-Site': 'same-origin'}, 403),
])
def test_dashboard_bridge_never_falls_back_from_invalid_identity_or_origin(local_setup, headers, status):
    _, app, client, *_ = local_setup
    app.state.local_open = True
    response = client.get('/api/v1/runtime-management/agents/subject/executors', headers=headers)
    assert response.status_code == status, response.text


def test_dashboard_bridge_rejects_unkeyed_nonlocal_server_and_has_no_ticket_routes(local_setup):
    _, app, client, headers, *_ = local_setup
    app.state.local_open = False
    assert client.get('/api/v1/runtime-management/agents/subject/executors').status_code == 401
    response = client.post('/api/v1/runtime-management/connections/executors', headers=headers['operator'], json={})
    assert response.status_code == 404
