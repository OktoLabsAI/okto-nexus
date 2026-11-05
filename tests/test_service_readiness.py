from __future__ import annotations

from importlib.metadata import version

from fastapi.testclient import TestClient
import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.http.lock import ServeLock
from okto_nexus.adapters.outbound.service_manager.identity import server_instance_id
from okto_nexus.application.service_lifecycle import project_server_readiness
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.domain.service_lifecycle import instance_id


def test_instance_identity_is_not_agent_project_or_service_generation():
    values = dict(component='server', home='/state', database='/state/nexus.db', principal='uid:1')
    expected = instance_id(**values)
    assert instance_id(**values) == expected
    for key, change in [('component', 'connector'), ('home', '/other'),
                        ('database', '/other.db'), ('principal', 'uid:2')]:
        assert instance_id(**{**values, key: change}) != expected


@pytest.mark.parametrize('startup,owned,closed,shutdown,state,queries', [
    (False, True, False, 'RUNNING', 'starting', False),
    (True, True, False, 'RUNNING', 'ready', True),
    (True, True, True, 'RUNNING', 'stopping', True),
    (True, True, False, 'DRAINING_PENDING', 'stopping', True),
    (True, False, False, 'RUNNING', 'failed', False),
])
def test_readiness_never_promises_harness_or_work_authority(startup, owned, closed, shutdown, state, queries):
    view = project_server_readiness(identity='svc_test', generation='generation', version='1.0',
        pid=1, owns_instance=owned, startup_complete=startup, admission_closed=closed,
        shutdown_state=shutdown).to_dict()
    assert view['state'] == state
    assert view['ready_for_queries'] is queries
    assert view['admission'] == ('canonical_scope_checks_required' if owned and not closed and shutdown == 'RUNNING' else 'closed')
    assert 'agent_id' not in view and 'harness_ready' not in view


@pytest.fixture
def running_service(tmp_path):
    home = tmp_path / 'home'
    with ServeLock(home) as lock:
        deps = bootstrap({}, ['--home', str(home)])
        app = build_app(deps, lock=lock)
        with TestClient(app, client=('127.0.0.1', 50000)) as client:
            yield client, app, lock, deps


def test_local_readiness_is_generation_correlated_read_only_and_captures_active_version(running_service, monkeypatch):
    client, app, lock, deps = running_service
    before = lock.path.read_bytes()
    expected = version('okto-nexus')
    monkeypatch.setattr('okto_nexus.adapters.inbound.http.service_lifecycle.version', lambda _: 'future-package')
    response = client.get('/api/v1/service')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    view = response.json()['data']
    assert view['instance_id'] == server_instance_id(lock.home_dir, lock.db_path)
    assert view['generation'] == lock.generation
    assert view['active_version'] == expected
    assert view['state'] == 'ready' and view['storage_initialized']
    assert view['admission'] == 'canonical_scope_checks_required'
    assert not deps.runtime_admission_fence.closed
    assert app.state.runtime_shutdown.status()['state'] == 'RUNNING'
    assert lock.path.read_bytes() == before
    # Canonical path aliases resolve to the same instance; no agent is involved.
    assert view['instance_id'] == server_instance_id(lock.home_dir / '..' / 'home', lock.db_path)


def test_participant_remote_operator_and_cross_origin_browser_cannot_inspect_service(running_service):
    client, app, _, _ = running_service
    created = client.post('/api/v1/agents', json={'agent_id': 'participant'})
    assert created.status_code == 200
    key = created.json()['data']['api_key']
    assert client.get('/api/v1/service', headers={'Authorization': 'Bearer ' + key}).status_code == 403
    assert client.get('/api/v1/service', headers={'Origin': 'https://untrusted.example'}).status_code == 403
    operator = client.post('/api/v1/agents/operator/regenerate-key').json()['data']['api_key']
    remote = TestClient(app, client=('192.0.2.10', 50000))
    assert remote.get('/api/v1/service', headers={'Authorization': 'Bearer ' + operator}).status_code == 403


def test_stopping_instance_stays_observable_without_reopening_admission(running_service):
    client, app, lock, deps = running_service
    deps.runtime_admission_fence.close()
    response = client.get('/api/v1/service').json()['data']
    assert response['state'] == 'stopping'
    assert response['ready_for_queries']
    assert response['admission'] == 'closed'
    assert lock.owned and deps.runtime_admission_fence.closed
    assert app.state.runtime_shutdown.status()['state'] == 'RUNNING'


def test_embedded_app_without_service_owner_does_not_fabricate_readiness(tmp_path):
    app = build_app(bootstrap({}, ['--home', str(tmp_path)]))
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        response = client.get('/api/v1/service')
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'SERVICE_IDENTITY_UNAVAILABLE'
