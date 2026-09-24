"""Production HTTP/MCP composition with synthetic peers, never real providers."""
import pytest
from test_pr34_remediation import runtime as runtime_fixture
from test_pr34_remediation import tool

runtime = runtime_fixture


def issue(client, operator, endpoint='endpoint-pi'):
    response = client.post('/api/v1/agents/worker/connection-keys', headers={'x-api-key': operator}, json={'endpoint_id': endpoint})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()['data']


def test_connection_key_opens_only_bound_identity_and_reuses(runtime):
    deps, client, _root, peers, operator, _caller = runtime
    issued = issue(client, operator)
    headers = issued['request']['headers']
    before = len(peers)
    for _ in range(2):
        response = client.post('/api/v1/connections/open', headers=headers, json={})
        assert response.status_code == 200, response.text
        assert response.json()['data']['agent_id'] == 'worker'
    assert len(peers) == before + 1
    assert response.json()['data']['reused'] is True
    assert client.post('/api/v1/connections/open', headers=headers, json={'agent_id': 'caller'}).status_code == 422
    assert client.get('/api/v1/agents', headers=headers).status_code == 401
    assert client.post('/api/v1/connections/open', json={}).status_code == 403
    assert client.post('/api/v1/connections/open', headers={'x-api-key': operator}, json={}).status_code == 401
    with deps.connection_factory.unit_of_work(write=False) as uow:
        worker = deps.repos.agents.get(uow, 'worker')
        assert worker.capabilities == {'review': True}
        assert worker.metadata == {'keep': 'profile'}
        row = uow.connection.execute('SELECT * FROM agent_connection_keys').fetchone()
        assert issued['connection_key'] not in str(dict(row))


def test_expiry_overrides_revocation_and_method_reenable(runtime):
    deps, client, _, peers, operator, _ = runtime
    headers = {'x-api-key': operator}
    path = '/api/v1/agents/worker/connections'
    view = client.get(path, headers=headers).json()['data']
    assert view['effective_key_ttl_seconds'] == 86400
    response = client.put(path, headers=headers, json={'expected_revision': 0, 'methods': {'pi': True}, 'key_ttl_seconds': 0})
    assert response.status_code == 200, response.text
    issued = issue(client, operator)
    assert issued['expires_at'] is None
    response = client.put(path, headers=headers, json={'expected_revision': 1, 'methods': {'pi': False}, 'key_ttl_seconds': None})
    assert response.status_code == 200
    assert client.post('/api/v1/connections/open', headers=issued['request']['headers'], json={}).status_code == 403
    assert not peers
    response = client.put(path, headers=headers, json={'expected_revision': 2, 'methods': {'pi': True}, 'key_ttl_seconds': 60})
    assert response.status_code == 200
    assert client.post('/api/v1/connections/open', headers=issued['request']['headers'], json={}).status_code == 403
    fresh = issue(client, operator)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_connection_keys SET expires_at='2000-01-01T00:00:00Z' WHERE key_id=?", (fresh['key_id'],))
    assert client.post('/api/v1/connections/open', headers=fresh['request']['headers'], json={}).status_code == 403
    fresh = issue(client, operator)
    assert client.delete('/api/v1/agents/worker/connection-keys/' + fresh['key_id'], headers=headers).status_code == 200
    assert client.post('/api/v1/connections/open', headers=fresh['request']['headers'], json={}).status_code == 403


def test_policy_admin_only_and_mcp_disabled(runtime):
    _, client, _, _, operator, caller = runtime
    path = '/api/v1/agents/caller/connections'
    assert client.get(path, headers={'x-api-key': caller}).status_code == 403
    assert client.post('/api/v1/agents/worker/connection-keys', headers={'x-api-key': caller}, json={'endpoint_id': 'endpoint-pi'}).status_code == 403
    response = client.put(path, headers={'x-api-key': operator}, json={'expected_revision': 0, 'methods': {'mcp': False}})
    assert response.status_code == 200, response.text
    response = client.post('/mcp/', headers={'x-api-key': caller}, json={})
    assert response.status_code == 403


@pytest.mark.parametrize('endpoint', ['endpoint-pi', 'endpoint-codex', 'endpoint-claude_code.stream'])
def test_all_managed_adapters_and_profile_invalidation(runtime, endpoint):
    _, client, _, _peers, operator, _ = runtime
    issued = issue(client, operator, endpoint)
    response = client.post('/api/v1/connections/open', headers=issued['request']['headers'], json={})
    assert response.status_code == 200, response.text
    profile = endpoint.replace('endpoint-', 'profile-')
    response = client.patch('/api/v1/harness/profiles/' + profile, headers={'x-api-key': operator}, json={'expected_revision': 1, 'enabled': False})
    assert response.status_code == 200
    assert client.post('/api/v1/connections/open', headers=issued['request']['headers'], json={}).status_code == 403


def test_mcp_bootstrap_parity_and_disable_blocks_operator_open(runtime):
    _, client, root, peers, operator, _ = runtime
    issued = tool(client, operator, 'harness_list', {'view': 'connections', 'maintenance': {
        'action': 'issue', 'agent_id': 'worker', 'endpoint_id': 'endpoint-pi'}})
    assert issued['ok'], issued
    saved = tool(client, operator, 'harness_list', {'view': 'connections', 'maintenance': {
        'action': 'configure', 'agent_id': 'worker', 'expected_revision': 0, 'methods': {'pi': False}, 'key_ttl_seconds': None}})
    assert saved['ok'], saved
    denied = tool(client, operator, 'harness_open', {'agent_id': 'worker', 'kind': 'pi', 'project_root': root, 'endpoint_id': 'endpoint-pi'})
    assert not denied['ok'], denied
    assert not peers


def test_concurrent_redemption_one_process_and_global_unlimited(runtime):
    from concurrent.futures import ThreadPoolExecutor

    _, client, _, peers, operator, _ = runtime
    response = client.patch('/api/v1/settings', headers={'x-api-key': operator}, json={'connection_key_ttl_seconds': 0})
    assert response.status_code == 200, response.text
    issued = issue(client, operator)
    assert issued['expires_at'] is None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.post('/api/v1/connections/open', headers=issued['request']['headers'], json={}), range(4)))
    assert any(r.status_code == 200 for r in results)
    assert all(r.status_code in {200, 409} for r in results), [r.text for r in results]
    assert len(peers) == 1


def test_disabled_feature_and_attach_opt_in(runtime):
    deps, client, _, peers, operator, _ = runtime
    issued = issue(client, operator)
    deps.config.feature_harness_integrations = False
    assert client.post('/api/v1/connections/open', headers=issued['request']['headers'], json={}).status_code == 403
    deps.config.feature_harness_integrations = True
    response = client.post('/api/v1/agents/worker/connection-keys', headers={'x-api-key': operator}, json={'endpoint_id': 'endpoint-claude_code.attach'})
    assert response.status_code == 403
    deps.config.feature_harness_attach = True
    issued = issue(client, operator, 'endpoint-claude_code.attach')
    response = client.post('/api/v1/connections/open', headers=issued['request']['headers'], json={})
    assert response.status_code == 200, response.text
    assert len(peers) == 1


def test_agent_bootstrap_retains_grant_expiry_and_revocation(runtime):
    from okto_nexus.application.auth import AgentKeyAuthService
    from okto_nexus.domain.base import iso_plus

    deps, client, _, peers, operator, _ = runtime
    with deps.connection_factory.unit_of_work() as uow:
        key = AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id='worker')
    expires = iso_plus(deps.clock.now_iso(), 600)
    response = client.post('/api/v1/harness/grants', headers={'x-api-key': operator}, json={
        'actor_agent_id': 'worker', 'endpoint_id': 'endpoint-pi', 'actions': ['open'], 'expires_at': expires})
    assert response.status_code == 200, response.text
    grant = response.json()['data']
    result = tool(client, key, 'harness_list', {'view': 'connections', 'maintenance': {
        'action': 'issue', 'agent_id': 'worker', 'endpoint_id': 'endpoint-pi'}})
    assert result['ok'], result
    assert result['data']['expires_at'] == expires
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_execution_grants SET revoked_at=? WHERE grant_id=?', (deps.clock.now_iso(), grant['grant_id']))
    assert client.post('/api/v1/connections/open', headers=result['data']['request']['headers'], json={}).status_code == 403
    assert not peers


def test_disable_stops_new_dispatch_and_preserves_inbox(runtime):
    from test_pr34_remediation import open_rest, send_message

    deps, client, _, peers, operator, _ = runtime
    assert open_rest(runtime).status_code == 200
    response = client.put('/api/v1/agents/worker/connections', headers={'x-api-key': operator}, json={
        'expected_revision': 0, 'methods': {'pi': False, 'codex': False, 'claude_code.stream': False, 'claude_code.attach': False}})
    assert response.status_code == 200, response.text
    sent = send_message(runtime)
    assert not sent.get('runtime_operations')
    assert not peers[0].sent
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM message_deliveries WHERE recipient_agent_id=?', ('worker',)).fetchone()[0] == 1


def test_stale_policy_update_rejected_without_mutation(runtime):
    _, client, _, _, operator, _ = runtime
    headers = {'x-api-key': operator}
    path = '/api/v1/agents/worker/connections'
    body = {'expected_revision': 0, 'methods': {'pi': False}, 'key_ttl_seconds': 10}
    assert client.put(path, headers=headers, json=body).status_code == 200
    body['key_ttl_seconds'] = 0
    assert client.put(path, headers=headers, json=body).status_code == 409
    assert client.get(path, headers=headers).json()['data']['key_ttl_seconds'] == 10


def test_old_runtime_writer_cannot_ignore_connection_policy(runtime):
    import sqlite3

    deps, client, _, _, operator, _ = runtime
    issue(client, operator)
    connection = deps.connection_factory.get_connection()
    try:
        # Removing a function registers a NULL stub on CPython; use a raw
        # connection to model a genuinely older process without this marker.
        connection.close()
        connection = sqlite3.connect(str(deps.config.db_path))
        connection.create_function('nexus_runtime_writer_v1', 0, lambda: 1)
        connection.create_function('nexus_runtime_admission_on', 0, lambda: 1)
        with pytest.raises(sqlite3.IntegrityError, match='runtime_writer_incompatible'):
            connection.execute("INSERT INTO runtime_open_requests(request_id,actor_agent_id,idempotency_key,request_hash,status,created_at) VALUES('legacy-open','worker','legacy','hash','RESERVED','2026-01-01')")
    finally:
        connection.close()


def test_global_ttl_shared_with_an_independent_stdio_composition(runtime):
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.adapters.inbound.mcp.tools.harness import build_access_service
    from okto_nexus.application.agent_connections import AgentConnectionService
    from okto_nexus.domain.runtime_context import RuntimeRequestContext

    deps, client, _, _, operator, _ = runtime
    assert client.patch('/api/v1/settings', headers={'x-api-key': operator}, json={'connection_key_ttl_seconds': 1234}).status_code == 200
    other = bootstrap({}, ['--home', str(deps.config.home_dir), '--feature-harness-integrations', 'true'])
    with other.connection_factory.unit_of_work(write=False) as uow:
        actor = other.repos.agents.get(uow, 'operator')
    context = RuntimeRequestContext('operator', 'agent_key', credential_binding=actor.api_key_hash)
    view = AgentConnectionService(build_access_service(other)).view(context, agent_id='worker')
    assert view['effective_key_ttl_seconds'] == 1234


@pytest.mark.parametrize('runtime', ['additional'], indirect=True)
def test_registered_extension_uses_the_same_connection_contract(runtime):
    _, client, _, peers, operator, _ = runtime
    view = client.get('/api/v1/agents/worker/connections', headers={'x-api-key': operator}).json()['data']
    assert any(m['method'] == 'fixture.additional.v1' for m in view['methods'])
    issued = issue(client, operator, 'endpoint-fixture.additional.v1')
    response = client.post('/api/v1/connections/open', headers=issued['request']['headers'], json={})
    assert response.status_code == 200, response.text
    assert len(peers) == 1


def test_upgrade_from_64_preserves_identity_and_is_idempotent(tmp_path):
    import shutil

    from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
    from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
    from okto_nexus.adapters.outbound.sqlite.migrations import (
        MigrationRunner,
        _default_migrations_dir,
    )
    from okto_nexus.config import NexusConfig

    old = tmp_path / 'old-migrations'
    old.mkdir()
    for migration in _default_migrations_dir().glob('*.sql'):
        if int(migration.name.split('_')[0]) <= 64:
            shutil.copy(migration, old)
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path / 'home'))
    MigrationRunner(factory, migrations_dir=old).apply()
    agents = SqliteAgentRepo()
    with factory.unit_of_work() as uow:
        agents.upsert(uow, agent_id='existing', role='reviewer', capabilities={'review': True}, metadata={'keep': 'profile'})
        before = agents.get(uow, 'existing')
    assert MigrationRunner(factory).apply() == [65]
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        assert agents.get(uow, 'existing') == before
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()


def test_disabling_mcp_fences_an_already_authenticated_stdio_connection(runtime):
    import asyncio
    import json
    import sys

    from test_pr34_remediation import stdio_environment

    deps, http, _, _, operator, _ = runtime

    async def query():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=sys.executable, args=[
            '-m', 'okto_nexus.adapters.inbound.mcp.server', '--home', str(deps.config.home_dir),
            '--feature-harness-integrations', 'true'], env=stdio_environment(runtime))
        async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
            await session.initialize()
            first = await session.call_tool('agent_whoami', {})
            assert (first.structuredContent or json.loads(first.content[0].text))['ok']
            response = http.put('/api/v1/agents/caller/connections', headers={'x-api-key': operator}, json={
                'expected_revision': 0, 'methods': {'mcp': False}})
            assert response.status_code == 200
            second = await session.call_tool('agent_whoami', {})
            assert (second.structuredContent or json.loads(second.content[0].text))['error']['code'] == 'PERMISSION_DENIED'

    asyncio.run(asyncio.wait_for(query(), timeout=30))
