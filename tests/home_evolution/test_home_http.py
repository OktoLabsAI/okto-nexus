"""Real ASGI middleware and application composition, without a provider."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from okto_nexus.bootstrap import dependencies, embedded_inventory
from okto_nexus.adapters.inbound.http.app import build_app


@pytest.fixture
def http(tmp_path, monkeypatch):
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=()))
    deps = dependencies.bootstrap({}, ['--home', str(tmp_path/'home'), '--feature-harness-integrations','false','--embedding-mode','off'])
    app = build_app(deps)
    with TestClient(app, client=('127.0.0.1',50000), base_url='http://localhost') as client:
        yield SimpleNamespace(client=client, app=app, deps=deps)


def test_overview_and_every_page_http_contract(http):
    for route in ('overview','work','results','activity','agents','external'):
        response = http.client.get('/api/v1/home/'+route)
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        result = response.json()['data']
        assert result['version'] == 1 and result['scope'] == {'workspace_id':None}
        assert result['server_id'] and result['snapshot_id']
    assert http.client.post('/api/v1/home/work', json={}).status_code == 405


def test_http_scope_parameters_and_target_are_closed(http):
    for params in ([('limit',1),('limit',2)], {'unexpected':'x'}, {'workspace_id':'all'}, {'limit':101}):
        response = http.client.get('/api/v1/home/work', params=params)
        assert response.status_code in (400,422), response.text
    for target in ('not-json', json.dumps({'kind':'arbitrary','url':'http://other'})):
        assert http.client.get('/api/v1/home/target', params={'target':target}).status_code in (400,422)


def test_remote_anonymous_does_not_inherit_loopback_operator(http):
    # A second HTTP peer reuses the active lifespan; it must not start a second
    # owner for the same application in another event loop.
    remote = TestClient(http.app, client=('192.0.2.20',50000), base_url='http://localhost')
    try:
        response = remote.get('/api/v1/home/overview')
        assert response.status_code in (401,403), response.text
        assert 'work' not in response.json().get('data',{})
    finally:
        remote.close()


def test_real_agent_and_monitor_keys_cannot_read_home_as_operator(http):
    for agent_id, role in (('worker','agent'),('monitor','monitor')):
        with http.deps.connection_factory.unit_of_work() as uow:
            http.deps.repos.agents.upsert(uow, agent_id=agent_id, role=role)
            key = http.app.state.auth.issue_key(uow, agent_id=agent_id)
        response = http.client.get('/api/v1/home/overview', headers={'X-API-Key':key})
        assert response.status_code in (401,403), response.text
        assert 'data' not in response.json() or 'work' not in response.json()['data']
