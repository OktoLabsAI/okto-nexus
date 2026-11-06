"""Passive observation through the real TCP authentication boundary."""
import json

import pytest

import test_pr34_remediation as fixtures
from test_pr34_remediation import tool
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.domain.coordination_requests import handoff_request_hash


runtime = fixtures.runtime
pytestmark = pytest.mark.parametrize('runtime', [False], indirect=True)
OLD = '2000-01-01T00:00:00.000000Z'


def seed(runtime):
    deps = runtime[0]
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id='passive-auth')
        target = {'strategy': 'direct', 'agent_id': 'worker'}
        deps.repos.handoffs.create(uow, handoff_id='passive-work', workspace_id='passive-auth',
            from_agent_id='caller', target=json.dumps(target), visibility='eligible',
            payload='Fixture work', status='OPEN')
        key = deps.repos.coordination_requests.key(uow, actor_agent_id='caller', workspace_id='passive-auth',
            operation='handoff_create', client_request_id='passive-request')
        deps.repos.coordination_requests.record(uow, key,
            request_hash=handoff_request_hash(target=target, visibility='eligible', payload='Fixture work'),
            now=deps.clock.now_iso(), resource_id='passive-work')
        uow.connection.execute("UPDATE agents SET last_seen_at=? WHERE agent_id='caller'", (OLD,))


def snapshot(runtime):
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        return {table: [tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)]
            for table in ('agents', 'sessions', 'messages', 'handoffs', 'coordination_requests',
                          'events', 'message_deliveries', 'delivery_outbox', 'execution_sessions',
                          'execution_leases', 'execution_operations')}


def rpc(runtime, method, params=None, *, notification=False, headers=None):
    body = {'jsonrpc': '2.0', 'method': method}
    if not notification:
        body['id'] = 1
    if params is not None:
        body['params'] = params
    return runtime[1].post('/mcp/', headers={
        'Authorization': 'Bearer ' + runtime[5], 'Accept': 'application/json, text/event-stream',
        **(headers or {})}, json=body)


def calls():
    yield 'initialize', {'protocolVersion': '2024-11-05', 'capabilities': {},
                         'clientInfo': {'name': 'passive-fixture', 'version': '1'}}
    for method in ('tools/list', 'resources/list', 'resources/templates/list', 'ping'):
        yield method, {}
    yield 'resources/read', {'uri': 'okto-nexus://reference/tool-docs/events'}
    yield 'tools/call', {'name': 'nexus_info', 'arguments': {}}
    yield 'tools/call', {'name': 'coordination_request_get', 'arguments': {
        'workspace_id': 'passive-auth', 'operation': 'handoff_create', 'client_request_id': 'passive-request'}}
    for name in ('event_get', 'event_cursor', 'event_wait', 'handoff_get'):
        arguments = {'workspace_id': 'passive-auth', 'agent_id': 'caller', 'passive': True}
        arguments.update({'handoff_id': 'passive-work'} if name == 'handoff_get' else {'stream': 'handoff'})
        yield 'tools/call', {'name': name, 'arguments': arguments}


@pytest.mark.parametrize('warm', [False, True], ids=['cold', 'warm'])
def test_tcp_passive_transport_discovery_and_reads_never_touch_agents(runtime, monkeypatch, warm):
    seed(runtime)
    if warm:
        assert tool(runtime[1], runtime[5], 'agent_whoami', {})['ok']
        with runtime[0].connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET last_seen_at=? WHERE agent_id='caller'", (OLD,))
    original = AgentKeyAuthService.resolve_readonly
    observed = []
    def fresh(self, uow, api_key):
        assert not uow._write
        stats = self.cache_stats()
        result = original(self, uow, api_key)
        assert self.cache_stats() == stats
        observed.append(stats['entries'])
        return result
    monkeypatch.setattr(AgentKeyAuthService, 'resolve_readonly', fresh)
    before = snapshot(runtime)
    for _ in range(2):
        participant = runtime[1].get('/v1/connections/participant',
            params={'workspace_id': 'passive-auth'}, headers={'Authorization': 'Bearer ' + runtime[5]})
        assert participant.status_code == 200, participant.text
        assert snapshot(runtime) == before
        for method, params in calls():
            response = rpc(runtime, method, params)
            assert response.status_code == 200, (method, response.text)
            assert snapshot(runtime) == before, (method, params.get('name'))
        initialized = rpc(runtime, 'notifications/initialized', notification=True)
        assert initialized.status_code in (200, 202, 204)
        assert snapshot(runtime) == before
        with runtime[1].stream('GET', '/mcp/', headers={
                'Authorization': 'Bearer ' + runtime[5], 'Accept': 'text/event-stream'}) as response:
            assert response.status_code in (200, 400, 405)
        deleted = runtime[1].delete('/mcp/', headers={'Authorization': 'Bearer ' + runtime[5]})
        assert deleted.status_code in (200, 400, 404, 405)
        assert snapshot(runtime) == before
    assert len(observed) == 32
    assert set(observed) == {1 if warm else 0}


@pytest.mark.parametrize('change', ['key', 'inactive'])
def test_tcp_passive_auth_ignores_warm_positive_cache_after_revocation(runtime, change):
    seed(runtime)
    assert tool(runtime[1], runtime[5], 'agent_whoami', {})['ok']  # populate middleware cache
    with runtime[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET last_seen_at=? WHERE agent_id='caller'", (OLD,))
        uow.connection.execute("UPDATE agents SET " + (
            "api_key_hash='out-of-band-rotation'" if change == 'key' else 'is_active=0') + " WHERE agent_id='caller'")
    before = snapshot(runtime)
    for method, params in calls():
        assert rpc(runtime, method, params).status_code == 401
    response = runtime[1].get('/v1/connections/participant', params={'workspace_id': 'passive-auth'},
        headers={'Authorization': 'Bearer ' + runtime[5]})
    assert response.status_code == 401
    assert snapshot(runtime) == before


def test_tcp_passive_classification_does_not_bypass_auth_or_legacy_activity(runtime):
    seed(runtime)
    before = snapshot(runtime)
    assert runtime[1].post('/mcp/', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
        headers={'Authorization': 'Bearer malformed', 'Accept': 'application/json, text/event-stream'}).status_code == 401
    assert snapshot(runtime) == before
    # An arbitrary header/argument does not make any other tool passive.
    response = rpc(runtime, 'tools/call', {'name': 'message_create', 'arguments': {
        'workspace_id': 'passive-auth', 'from_agent_id': 'caller', 'subject': 'Fixture',
        'body': 'Explicit productive action', 'target': {'strategy': 'direct', 'agent_id': 'worker'}}},
        headers={'X-Nexus-Passive': 'true'})
    assert response.status_code == 200
    with runtime[0].connection_factory.unit_of_work(write=False) as uow:
        assert runtime[0].repos.agents.get(uow, 'caller').last_seen_at != OLD
        assert uow.connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 1
    for value in (False, 'true', 1, None):
        with runtime[0].connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET last_seen_at=? WHERE agent_id='caller'", (OLD,))
        rpc(runtime, 'tools/call', {'name': 'event_cursor', 'arguments': {
            'workspace_id': 'passive-auth', 'agent_id': 'caller', 'stream': 'handoff', 'passive': value}})
        with runtime[0].connection_factory.unit_of_work(write=False) as uow:
            assert runtime[0].repos.agents.get(uow, 'caller').last_seen_at != OLD
