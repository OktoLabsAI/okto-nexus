"""Authenticated self discovery/opening through actual HTTP/MCP and owner proxy."""
import asyncio
import json
import sys

import pytest
from test_pr34_remediation import runtime as runtime_fixture
from test_pr34_remediation import stdio_environment, tool

from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.domain.base import iso_plus

runtime = runtime_fixture


def worker_key(runtime):
    deps = runtime[0]
    with deps.connection_factory.unit_of_work() as uow:
        return AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id="worker")


def grant(runtime, actor="worker", endpoint="endpoint-pi"):
    deps, client, _, _, operator, _ = runtime
    result = client.post('/api/v1/harness/grants', headers={'x-api-key': operator}, json={
        'actor_agent_id': actor, 'endpoint_id': endpoint, 'actions': ['open', 'discover'],
        'expires_at': iso_plus(deps.clock.now_iso(), 600)})
    assert result.status_code == 200
    return result.json()['data']['grant_id']


def available(runtime, key):
    result = tool(runtime[1], key, 'harness_list', {'view': 'connections', 'maintenance': {'action': 'available'}})
    assert result['ok'], result
    return result['data']


def test_self_discovery_is_scoped_read_only_and_reports_authorized_open(runtime):
    deps, client, root, peers, _, caller = runtime
    key = worker_key(runtime)
    before = available(runtime, key)
    assert before['agent_id'] == 'worker'
    assert not next(m for m in before['methods'] if m['method'] == 'pi')['available']
    assert all(not m['endpoints'] for m in available(runtime, caller)['methods'])
    assert root not in json.dumps(before)
    assert 'profile-pi' not in json.dumps(before)
    assert not peers
    grant(runtime)
    view = available(runtime, key)
    assert client.get('/api/v1/connections/available', headers={'x-api-key': key}).json()['data'] == view
    pi = next(m for m in view['methods'] if m['method'] == 'pi')
    assert pi['available']
    call = pi['endpoints'][0]['connect']
    call['arguments']['maintenance']['idempotency_key'] = 'self-open-fixture'
    first = tool(client, key, call['tool'], call['arguments'])
    assert first['ok'], first
    second = client.post('/api/v1/connections/connect', headers={'x-api-key': key}, json={
        'endpoint_id': 'endpoint-pi', 'idempotency_key': 'self-open-fixture'})
    assert second.status_code == 200 and second.json()['data']['reused']
    assert len(peers) == 1
    assert client.post('/api/v1/connections/connect', headers={'x-api-key': key}, json={
        'endpoint_id': 'endpoint-pi', 'idempotency_key': 'spoof', 'agent_id': 'caller'}).status_code == 422
    assert not tool(client, key, 'harness_list', {'view': 'connections', 'maintenance': {
        'action': 'available', 'agent_id': 'caller'}})['ok']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM agent_connection_keys').fetchone()[0] == 0


def test_self_open_rechecks_grants_and_rejects_foreign_endpoint(runtime):
    _deps, client, _, peers, operator, caller = runtime
    key = worker_key(runtime)
    gid = grant(runtime)
    assert next(m for m in available(runtime, key)['methods'] if m['method'] == 'pi')['available']
    assert client.delete('/api/v1/harness/grants/' + gid, headers={'x-api-key': operator}).status_code == 200
    body = {'endpoint_id': 'endpoint-pi', 'idempotency_key': 'revoked'}
    assert client.post('/api/v1/connections/connect', headers={'x-api-key': key}, json=body).status_code == 403
    grant(runtime, actor='caller')
    assert client.post('/api/v1/connections/connect', headers={'x-api-key': caller}, json=body).status_code == 403
    grant(runtime)
    assert client.put('/api/v1/agents/worker/connections', headers={'x-api-key': operator}, json={
        'expected_revision': 0, 'methods': {'pi': False}}).status_code == 200
    assert client.post('/api/v1/connections/connect', headers={'x-api-key': key}, json=body).status_code == 403
    assert not peers


def test_actual_stdio_self_discovery_and_connect_use_existing_serve_owner(runtime):
    deps, _, _, peers, _, _ = runtime
    key = worker_key(runtime)
    grant(runtime)

    async def run():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        env = stdio_environment(runtime)
        env['OKTO_NEXUS_API_KEY'] = key
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'okto_nexus.adapters.inbound.mcp.server', '--home', str(deps.config.home_dir)], env=env)
        async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
            await session.initialize()
            response = await session.call_tool('harness_list', {'view': 'connections', 'maintenance': {'action': 'available'}})
            result = response.structuredContent or json.loads(response.content[0].text)
            assert result['ok'] and result['data']['agent_id'] == 'worker'
            for _ in range(2):
                response = await session.call_tool('harness_list', {'view': 'connections', 'maintenance': {
                    'action': 'connect', 'endpoint_id': 'endpoint-pi', 'idempotency_key': 'stdio-self-fixture'}})
                result = response.structuredContent or json.loads(response.content[0].text)
                assert result['ok'], result
            assert result['data']['reused']
    asyncio.run(asyncio.wait_for(run(), timeout=45))
    assert len(peers) == 1 and peers[0].session.owning_agent_id == 'worker'


def test_self_connect_never_forwards_with_another_identity(runtime, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools import harness

    _, client, _, peers, operator, _ = runtime
    key = worker_key(runtime)
    grant(runtime)
    monkeypatch.setattr(harness, 'is_local_runtime_owner', lambda deps: False)
    monkeypatch.setenv('OKTO_NEXUS_API_KEY', operator)
    response = client.post('/api/v1/connections/connect', headers={'x-api-key': key}, json={
        'endpoint_id': 'endpoint-pi', 'idempotency_key': 'wrong-proxy-principal'})
    assert response.status_code == 403
    assert not peers


def test_self_open_revalidates_grant_after_reservation_before_native_start(runtime, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools import harness

    deps, client, _, peers, _, _ = runtime
    key = worker_key(runtime)
    gid = grant(runtime)
    construct = harness.construct_profile_connector

    def revoke_after_reservation(*args, **kwargs):
        with deps.connection_factory.unit_of_work() as uow:
            harness.build_access_service(deps).grants.revoke(uow, grant_id=gid, now=deps.clock.now_iso())
        return construct(*args, **kwargs)

    # Committed operator revocation after reserve, before the native effect.
    monkeypatch.setattr(harness, 'construct_profile_connector', revoke_after_reservation)
    response = client.post('/api/v1/connections/connect', headers={'x-api-key': key}, json={
        'endpoint_id': 'endpoint-pi', 'idempotency_key': 'revoke-before-native'})
    assert response.status_code == 403
    assert all(peer.session is None for peer in peers)


@pytest.mark.parametrize("runtime", ["additional"], indirect=True)
def test_registered_adapter_uses_self_discovery_and_connect(runtime):
    key = worker_key(runtime)
    grant(runtime, endpoint='endpoint-fixture.additional.v1')
    item = next(m for m in available(runtime, key)['methods'] if m['method'] == 'fixture.additional.v1')
    assert item['available']
    arguments = item['endpoints'][0]['connect']['arguments']
    arguments['maintenance']['idempotency_key'] = 'additional-adapter-self'
    result = tool(runtime[1], key, 'harness_list', arguments)
    assert result['ok'], result
    assert result['data']['owning_agent_id'] == 'worker'
    assert len(runtime[3]) == 1
