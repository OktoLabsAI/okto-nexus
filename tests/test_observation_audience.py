"""OBS transport routing, without substituting shape checks for token admission.

The injected routes expose only the middleware context. Stored token authority,
generation fences and admission belong to the observation service's own tests.
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from okto_nexus.adapters.inbound.http.app import ApiKeyAuthMiddleware, build_app, ensure_operator_key
from okto_nexus.adapters.inbound.http.identity_ctx import current_agent, runtime_request_context
from okto_nexus.adapters.inbound.http.operator_auth import COOKIE
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.domain.execution_principal import current_execution_principal
from okto_nexus.domain.observation_tokens import generate_observation_token


PUBLISH = '/v1/observations/activity'
MANAGEMENT = '/api/v1/observations/sources'
OLD = '2000-01-01T00:00:00.000000Z'


@pytest.fixture
def environment(tmp_path, monkeypatch):
    from okto_nexus.bootstrap import embedded_inventory
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
                        lambda **_: SimpleNamespace(candidates=()))
    deps = bootstrap({}, ['--home', str(tmp_path), '--feature-harness-integrations', 'false',
                          '--embedding-mode', 'off'])
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    ensure_operator_key(deps, auth)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id='publisher')
        key = auth.issue_key(uow, agent_id='publisher')
        uow.connection.execute('UPDATE agents SET last_seen_at=?', (OLD,))
    app = build_app(deps)
    calls = []

    async def context_probe(request: Request):
        context = runtime_request_context()
        agent = current_agent.get()
        result = {
            'actor_agent_id': context.actor_agent_id,
            'authentication_source': context.authentication_source,
            'trusted_local_operator': context.trusted_local_operator,
            'credential_binding': context.credential_binding,
            'current_agent': agent.agent_id if agent else None,
            'execution_principal': current_execution_principal.get() is not None,
        }
        calls.append((request.method, request.url.path))
        return result

    # Place probes before eventual production routes without modifying their
    # wiring or claiming that a syntactically valid token was authenticated.
    app.router.routes[:0] = [
        APIRoute(PUBLISH, context_probe, methods=['POST']),
        APIRoute('/api/v1/observations', context_probe,
                 methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE']),
        APIRoute(MANAGEMENT, context_probe,
                 methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE']),
    ]
    return SimpleNamespace(deps=deps, app=app, key=key, calls=calls)


def snapshot(env):
    """Compare every persisted table, including agents and runtime/presence."""
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        names = [row[0] for row in uow.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name: sorted((tuple(row) for row in uow.connection.execute(
            'SELECT * FROM "' + name.replace('"', '""') + '"')), key=repr) for name in names}


def bearer(token):
    return {'Authorization': 'Bearer ' + token}


def forbid_canonical_resolution(env, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('OBS audience routing attempted canonical or human authentication')
    monkeypatch.setattr(AgentKeyAuthService, 'resolve', forbidden)
    monkeypatch.setattr(AgentKeyAuthService, 'resolve_readonly', forbidden)
    monkeypatch.setattr(env.app.state.operator_auth, 'resolve', forbidden)


def test_publish_shape_only_reaches_exact_route_without_promoting_identity(environment, monkeypatch):
    env = environment
    with TestClient(env.app, client=('127.0.0.1', 50000)) as client:
        before = snapshot(env)
        forbid_canonical_resolution(env, monkeypatch)
        response = client.post(PUBLISH, headers=bearer(generate_observation_token()), json={})
        assert response.status_code == 200, response.text
        assert response.json() == {
            'actor_agent_id': None, 'authentication_source': 'unauthenticated',
            'trusted_local_operator': False, 'credential_binding': None,
            'current_agent': None, 'execution_principal': False,
        }
        assert env.calls == [('POST', PUBLISH)]
        assert snapshot(env) == before


def test_publish_rejects_other_credentials_and_substitutes_before_route(environment, monkeypatch):
    env = environment
    token = generate_observation_token()
    env.app.state.operator_auth.configure(username='human', password='test-password-123', local=True)
    session = env.app.state.operator_auth.login('human', 'test-password-123')
    with TestClient(env.app, client=('127.0.0.1', 50000)) as client:
        client.cookies.set(COOKIE, session)
        before = snapshot(env)
        forbid_canonical_resolution(env, monkeypatch)
        invalid = [
            {}, {'headers': bearer(env.key)}, {'headers': bearer('nxsept_' + 'a' * 64)},
            {'headers': bearer('nxc4_' + 'a' * 64)}, {'headers': bearer('nxt4_' + 'a' * 64)},
            {'headers': bearer(session)}, {'headers': {'x-api-key': token}},
            {'params': {'api_key': token}}, {'headers': bearer('nxobs_short')},
            {'headers': bearer('nxobs_' + 'A' * 64)},
            {'headers': {**bearer(token), 'x-api-key': ''}},
            {'headers': bearer(token), 'params': {'api_key': ''}},
            {'headers': {**bearer(token), 'x-api-key': env.key}},
            {'headers': bearer(token), 'params': {'api_key': env.key}},
            {'headers': [('Authorization', 'Bearer ' + token), ('Authorization', 'Bearer ' + env.key)]},
        ]
        for kwargs in invalid:
            response = client.post(PUBLISH, json={}, **kwargs)
            assert response.status_code == 401, response.text
            assert response.json()['error']['code'] == 'AUTH_FAILED'
        assert not env.calls
        assert snapshot(env) == before


def test_obs_family_cannot_enter_any_other_audience_or_public_exception(environment, monkeypatch):
    env = environment
    token = generate_observation_token()
    with TestClient(env.app, client=('127.0.0.1', 50000), follow_redirects=False) as client:
        before = snapshot(env)
        forbid_canonical_resolution(env, monkeypatch)
        endpoints = [
            ('GET', PUBLISH), ('PUT', PUBLISH), ('OPTIONS', PUBLISH), ('POST', PUBLISH + '/'),
            ('POST', '/mcp/'), ('GET', '/mcp/'), ('DELETE', '/mcp/'),
            ('GET', '/api/v1/events'), ('GET', '/api/v1/inbox/peek'),
            ('GET', '/api/v1/observations'), ('POST', MANAGEMENT),
            ('POST', '/api/v1/agents/publisher/regenerate-key'), ('POST', '/api/v1/operator-auth/login'),
            ('GET', '/v1/connections/participant'), ('POST', '/v1/runtime/native-actions'),
            ('PUT', '/v1/runtime/executors/fixture/inventory'),
            ('POST', '/v1/runtime/executors/fixture/inventory:claim-refresh'),
            ('POST', '/v1/runtime/operations/fixture/receipts'),
            ('GET', '/healthz'), ('GET', '/assets/fixture.js'),
        ]
        for method, path in endpoints:
            response = client.request(method, path, headers=bearer(token))
            assert response.status_code == 401, (method, path, response.text)
        # A higher-precedence canonical credential cannot conceal an OBS token.
        for kwargs in [
            {'params': {'api_key': env.key}, 'headers': bearer(token)},
            {'params': {'api_key': token}, 'headers': bearer(env.key)},
            {'params': {'api_key': env.key}, 'headers': {'x-api-key': token}},
            {'params': [('api_key', env.key), ('api_key', token)]},
            {'headers': bearer('nxobs_malformed')},
        ]:
            assert client.get(MANAGEMENT, **kwargs).status_code == 401
        assert not env.calls
        assert snapshot(env) == before


def test_valid_shape_without_installed_publish_route_returns_not_found():
    # No deps/auth state is supplied: this path must not consult canonical auth,
    # and middleware must not manufacture a successful publication response.
    app = FastAPI()
    app.add_middleware(ApiKeyAuthMiddleware)
    with TestClient(app) as client:
        response = client.post(PUBLISH, headers=bearer(generate_observation_token()))
        assert response.status_code == 404


@pytest.mark.parametrize('warm', [False, True], ids=['cold', 'warm'])
def test_management_auth_is_fresh_readonly_for_every_method_and_retains_key_binding(environment, warm):
    env = environment
    with TestClient(env.app) as client:
        if warm:
            assert client.get('/api/v1/agents', headers=bearer(env.key)).status_code == 200
        with env.deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE agents SET last_seen_at=?', (OLD,))
            expected_hash = env.deps.repos.agents.get(uow, 'publisher').api_key_hash
        before = snapshot(env)
        cache = env.app.state.auth.cache_stats()
        for path in ('/api/v1/observations', MANAGEMENT):
            for method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
                response = client.request(method, path, headers=bearer(env.key), json={})
                assert response.status_code == 200, response.text
                assert response.json() == {
                    'actor_agent_id': 'publisher', 'authentication_source': 'agent_key',
                    'trusted_local_operator': False, 'credential_binding': expected_hash,
                    'current_agent': 'publisher', 'execution_principal': False,
                }
        assert env.app.state.auth.cache_stats() == cache
        assert snapshot(env) == before


@pytest.mark.parametrize('change', ['key', 'inactive'])
def test_management_rejects_revocation_despite_warm_auth_cache(environment, change):
    env = environment
    with TestClient(env.app) as client:
        assert client.get('/api/v1/agents', headers=bearer(env.key)).status_code == 200
        with env.deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE agents SET ' + (
                "api_key_hash='rotated'" if change == 'key' else 'is_active=0') +
                " WHERE agent_id='publisher'")
        before = snapshot(env)
        for method in ('GET', 'POST', 'PATCH', 'DELETE'):
            assert client.request(method, MANAGEMENT, headers=bearer(env.key)).status_code == 401
        assert not env.calls
        assert snapshot(env) == before


@pytest.mark.parametrize('human', [False, True], ids=['local-operator', 'operator-session'])
def test_management_preserves_trusted_operator_context_without_publish_authority(environment, human):
    env = environment
    host = '192.0.2.20' if human else '127.0.0.1'
    with TestClient(env.app, client=(host, 50000)) as client:
        if human:
            env.app.state.operator_auth.configure(username='human', password='test-password-123', local=True)
            client.cookies.set(COOKIE, env.app.state.operator_auth.login('human', 'test-password-123'))
        before = snapshot(env)
        response = client.post(MANAGEMENT, headers={'x-nexus-ui': '1', 'Origin': 'http://testserver'}) if human else client.post(MANAGEMENT)
        assert response.status_code == 200, response.text
        context = response.json()
        assert context['authentication_source'] == ('operator_session' if human else 'http_loopback')
        assert context['trusted_local_operator'] is True
        assert context['credential_binding'] is None
        assert context['actor_agent_id'] is None
        assert client.post(PUBLISH).status_code == 401
        assert snapshot(env) == before
