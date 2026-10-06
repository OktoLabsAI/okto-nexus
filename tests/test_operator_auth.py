"""Human dashboard sessions never authenticate agent transports."""
import hashlib

import pytest
from fastapi.testclient import TestClient

from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
from okto_nexus.adapters.inbound.http.operator_auth import COOKIE, OperatorAuth

HEADERS = {'x-nexus-ui': '1', 'Origin': 'http://testserver'}
ACCOUNT = {'username': 'human', 'password': 'test-password-123'}


@pytest.fixture
def app(tmp_path):
    deps = bootstrap({}, ['--home', str(tmp_path), '--feature-harness-integrations', 'false', '--embedding-mode', 'off'])
    return build_app(deps)


def test_local_setup_remote_login_logout_and_transport_separation(app):
    local = TestClient(app, client=('127.0.0.1', 5000), base_url='http://localhost')
    assert local.get('/api/v1/operator-auth/status').json()['data']['local']
    assert local.get('/api/v1/agents').status_code == 200
    response = local.post('/api/v1/operator-auth/account', json=ACCOUNT,
                          headers={'x-nexus-ui': '1', 'Origin': 'http://localhost'})
    assert response.status_code == 200, response.text
    local.close()
    with TestClient(app, client=('192.168.0.116', 5000)) as remote:
        assert remote.get('/api/v1/agents').status_code == 401
        assert remote.post('/api/v1/operator-auth/account', json=ACCOUNT, headers=HEADERS).status_code == 403
        response = remote.post('/api/v1/operator-auth/login', json=ACCOUNT, headers=HEADERS)
        assert response.status_code == 200
        assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
        assert remote.get('/api/v1/operator-auth/status').json()['data']['username'] == 'human'
        assert remote.get('/api/v1/agents').status_code == 200
        assert remote.post('/api/v1/agents', json={'agent_id': 'created-by-human'}, headers=HEADERS).status_code < 300
        assert remote.post('/mcp', json={}).status_code == 401
        assert remote.get('/v1/connections/me').status_code == 401
        token = remote.cookies.get(COOKIE)
        assert remote.post('/api/v1/operator-auth/logout', headers=HEADERS).status_code == 200
        assert remote.get('/api/v1/agents').status_code == 401
        remote.cookies.set(COOKIE, token)
        assert remote.get('/api/v1/agents').status_code == 401
    with app.state.operator_auth.db() as db:
        assert db.execute("SELECT username FROM audit WHERE action='POST' AND path='/api/v1/agents'").fetchone()[0] == 'human'


@pytest.mark.parametrize('headers', [{}, {'x-nexus-ui': '1', 'Origin': 'https://evil.example'},
                                    {'x-nexus-ui': '1', 'Sec-Fetch-Site': 'cross-site'}])
def test_remote_session_rejects_cross_origin_mutations(app, headers):
    auth = app.state.operator_auth
    auth.configure(**ACCOUNT, local=True)
    with TestClient(app) as client:
        client.cookies.set(COOKIE, auth.login(**ACCOUNT))
        assert client.post('/api/v1/agents', json={'agent_id': 'blocked'}, headers=headers).status_code == 403
        assert client.post('/api/v1/operator-auth/account', json=ACCOUNT, headers=headers).status_code == 403


def test_password_change_revokes_sessions_and_requires_current_password_remotely(app):
    auth = app.state.operator_auth
    auth.configure(**ACCOUNT, local=True)
    token = auth.login(**ACCOUNT)
    with TestClient(app) as client:
        client.cookies.set(COOKIE, token)
        changed = {**ACCOUNT, 'password': 'new-password-123'}
        assert client.post('/api/v1/operator-auth/account', json=changed, headers=HEADERS).status_code == 403
        response = client.post('/api/v1/operator-auth/account', json={**changed, 'current_password': ACCOUNT['password']}, headers=HEADERS)
        assert response.status_code == 200
        assert auth.resolve(token) is None
        assert auth.login(**ACCOUNT) is None
        assert auth.login(**changed)


def test_session_hashes_expiry_persistence_and_login_throttle(tmp_path):
    auth = OperatorAuth(tmp_path)
    auth.configure(**ACCOUNT, local=True)
    token = auth.login(**ACCOUNT)
    assert OperatorAuth(tmp_path).resolve(token) == 'human'
    with auth.db() as db:
        assert db.execute('SELECT digest FROM sessions').fetchone()[0] == hashlib.sha256(token.encode()).hexdigest()
        assert db.execute('SELECT digest FROM account').fetchone()[0] != ACCOUNT['password']
        db.execute('UPDATE sessions SET expires=0')
    assert auth.resolve(token) is None
    for _ in range(5):
        assert auth.login('human', 'wrong') is None
    assert auth.login(**ACCOUNT) is None


def test_agent_key_cannot_configure_human_account_and_still_authenticates_agent(app):
    _, key = ensure_operator_key(app.state.deps, app.state.auth)
    with TestClient(app) as client:
        headers = {**HEADERS, 'x-api-key': key}
        assert client.get('/api/v1/agents', headers=headers).status_code == 200
        assert client.post('/api/v1/operator-auth/account', json=ACCOUNT, headers=headers).status_code == 403
        assert client.get('/v1/connections/me', headers={'Authorization': f'Bearer {key}'}).status_code == 200


def test_forwarding_headers_cannot_enable_local_trust(app):
    with TestClient(app, client=('127.0.0.1', 5000)) as client:
        headers = {'x-forwarded-for': '192.168.0.116'}
        assert not client.get('/api/v1/operator-auth/status', headers=headers).json()['data']['local']
        assert client.get('/api/v1/agents', headers=headers).status_code == 401
        assert client.post('/api/v1/operator-auth/account', json=ACCOUNT, headers={**headers, **HEADERS}).status_code == 403


def test_https_session_cookie_is_secure(app):
    app.state.operator_auth.configure(**ACCOUNT, local=True)
    with TestClient(app, base_url='https://testserver') as client:
        result = client.post('/api/v1/operator-auth/login', json=ACCOUNT,
                             headers={'Origin': 'https://testserver', 'x-nexus-ui': '1'})
        assert 'Secure' in result.headers['set-cookie']


def test_validation_never_echoes_password(app):
    with TestClient(app) as client:
        response = client.post('/api/v1/operator-auth/account',
                               json={'username': 'human', 'password': 'secret'}, headers=HEADERS)
        assert response.status_code == 422
        assert 'secret' not in response.text
