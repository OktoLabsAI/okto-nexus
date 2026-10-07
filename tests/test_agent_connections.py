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






@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_policy_admin_only_and_mcp_disabled(runtime):
    deps, client, _, _, operator, caller = runtime
    path = '/api/v1/agents/caller/connections'
    assert client.get(path, headers={'x-api-key': caller}).status_code == 403
    assert client.post('/api/v1/agents/worker/connection-keys', headers={'x-api-key': caller}, json={'endpoint_id': 'endpoint-pi'}).status_code == 404
    # Retained pre-cutover MCP denials still fence authenticated traffic.
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agent_connection_methods(agent_id,method,enabled) VALUES('caller','mcp',0)")
    response = client.post('/mcp/', headers={'x-api-key': caller}, json={})
    assert response.status_code == 403












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


@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_stale_policy_update_rejected_without_mutation(runtime):
    _, client, _, _, operator, _ = runtime
    headers = {'x-api-key': operator}
    path = '/api/v1/agents/worker/execution-policy'
    body = {'expected_revision': 0, 'execution_location': 'remote'}
    assert client.put(path, headers=headers, json=body).status_code == 200
    body['execution_location'] = 'local'
    assert client.put(path, headers=headers, json=body).status_code == 409
    assert client.get(path, headers=headers).json()['data']['execution_location'] == 'remote'


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


@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
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
        # Seed with the old schema, without invoking the current repository.
        uow.connection.execute("INSERT INTO agents(agent_id,role,capabilities,metadata,created_at) "
            "VALUES('existing','reviewer',?,?,'2026-10-01')",
            ('{"review":true}', '{"keep":"profile"}'))
        before = dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='existing'").fetchone())
    expected = sorted(int(path.name.split("_")[0])
                      for path in _default_migrations_dir().glob("*.sql")
                      if int(path.name.split("_")[0]) > 64)
    assert MigrationRunner(factory).apply() == expected
    assert MigrationRunner(factory).apply() == []
    with factory.unit_of_work(write=False) as uow:
        after = dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='existing'").fetchone())
        assert {key: after[key] for key in before} == before
        assert after['deleted_at'] is None
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()


@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_disabling_mcp_fences_an_already_authenticated_http_client(runtime):
    # R4 serves stateless HTTP MCP. Reuse the authenticated HTTP connection;
    # a prior successful call must not cache permission past a policy change.
    deps, http, _, peers, operator, caller = runtime
    before = len(peers)
    assert tool(http, caller, 'agent_whoami', {})['ok']
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agent_connection_methods(agent_id,method,enabled) VALUES('caller','mcp',0)")
    refused = http.post('/mcp/', headers={'Authorization': 'Bearer ' + caller,
        'Accept': 'application/json, text/event-stream'}, json={
            'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
            'params': {'name': 'agent_whoami', 'arguments': {}}})
    assert refused.status_code == 403
    assert refused.json()['error']['code'] == 'PERMISSION_DENIED'
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_connection_methods SET enabled=1 WHERE agent_id='caller' AND method='mcp'")
    assert tool(http, caller, 'agent_whoami', {})['ok']
    assert len(peers) == before


@pytest.mark.parametrize('runtime', [False], indirect=True)
def test_enabling_feature_does_not_restore_retired_setup(runtime):
    deps, client, root, peers, operator, _ = runtime
    deps.config.feature_harness_integrations = True
    headers = {'x-api-key': operator}
    for route, body in (
        ('profiles', {'profile_id': 'profile-pi', 'adapter_id': 'pi', 'enabled': True}),
        ('endpoints', {'endpoint_id': 'endpoint-pi', 'agent_id': 'worker', 'adapter_id': 'pi',
                       'project_root': root, 'profile_id': 'profile-pi', 'enabled': True}),
    ):
        response = client.post('/api/v1/harness/' + route, headers=headers, json=body)
        assert response.status_code == 422, response.text
        assert 'canonical runtime integration' in response.json()['error']['message']
    assert not peers


def test_self_bootstrap_rechecks_permissions_at_the_native_start_boundary(runtime, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools import harness
    from okto_nexus.application.auth import AgentKeyAuthService
    from okto_nexus.domain.base import iso_plus

    deps, client, _, peers, operator, _ = runtime
    with deps.connection_factory.unit_of_work() as uow:
        key = AgentKeyAuthService(deps.repos.agents, deps.clock).issue_key(uow, agent_id='worker')
    response = client.post('/api/v1/harness/grants', headers={'x-api-key': operator}, json={
        'actor_agent_id': 'worker', 'endpoint_id': 'endpoint-pi', 'actions': ['open'],
        'expires_at': iso_plus(deps.clock.now_iso(), 600)})
    assert response.status_code == 200
    issued = issue(client, key)
    construct = harness.construct_profile_connector

    def change_permission_after_reservation(*args, **kwargs):
        # A separate committed operator change after admission/reservation,
        # before the real supervisor validates and starts the external peer.
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE agents SET permissions=? WHERE agent_id=?',
                ('{"messages":{"send_direct":false}}', 'worker'))
        return construct(*args, **kwargs)

    monkeypatch.setattr(harness, 'construct_profile_connector', change_permission_after_reservation)
    response = client.post('/api/v1/connections/open', headers=issued['request']['headers'], json={})
    assert response.status_code in {403, 409}, response.text
    assert all(peer.session is None for peer in peers)


@pytest.mark.parametrize("runtime", ["unconfigured"], indirect=True)
def test_global_expiry_does_not_coerce_fraction_or_boolean_to_unlimited(runtime):
    _, client, _, _, operator, _ = runtime
    headers = {'x-api-key': operator}
    for invalid in (False, True, 0.5, '0', None, -1, 315360001):
        response = client.patch('/api/v1/settings', headers=headers, json={'connection_key_ttl_seconds': invalid})
        assert response.status_code == 422, (invalid, response.text)
    assert client.get('/api/v1/agents/worker/connections', headers=headers).json()['data']['effective_key_ttl_seconds'] == 86400
