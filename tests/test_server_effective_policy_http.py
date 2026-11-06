"""Real HTTP settings and Server lifespan, using isolated OS-held ServeLocks.

Provider discovery is empty; these tests qualify Server ownership and SQLite
transactions, not execution by any installed personal provider.
"""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient  # noqa: E402

from okto_nexus.adapters.inbound.http.app import build_app  # noqa: E402
from okto_nexus.adapters.inbound.http.lock import ServeLock  # noqa: E402
from okto_nexus.adapters.inbound.mcp.server import bootstrap  # noqa: E402
from okto_nexus.errors import ErrorCode, OktoNexusError  # noqa: E402

KEYS = ('feature_harness_integrations', 'feature_hitl')


@pytest.fixture(autouse=True)
def isolated_inventory(monkeypatch):
    from okto_nexus.bootstrap import embedded_inventory
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
                        lambda **_: SimpleNamespace(candidates=()))


def rows(deps, table='server_effective_policy'):
    assert table in {'server_effective_policy', 'settings'}
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return [dict(row) for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY key')]


def live(deps):
    return {key: getattr(deps.config, key) for key in KEYS}


def policy(deps):
    return {row['key']: row for row in rows(deps)}


@contextmanager
def server(home, *, env=None):
    deps = bootstrap(env or {}, ['--home', str(home), '--embedding-mode', 'off'])
    lock = ServeLock(deps.config.home_dir, db_path=deps.config.db_path)
    lock.acquire()
    try:
        app = build_app(deps, lock=lock)
        with TestClient(app, client=('127.0.0.1', 50000), raise_server_exceptions=False) as client:
            yield deps, app, client, lock
    finally:
        lock.release()
        deps.connection_factory.close()


def test_bootstrap_and_unowned_http_app_do_not_publish_server_policy(tmp_path):
    deps = bootstrap({}, ['--home', str(tmp_path / 'home'), '--embedding-mode', 'off'])
    try:
        assert rows(deps) == []
        app = build_app(deps)
        assert rows(deps) == []
        with TestClient(app, client=('127.0.0.1', 50000)) as client:
            assert rows(deps) == []
            assert client.patch('/api/v1/settings', json={'feature_hitl': True}).status_code == 200
            assert deps.config.feature_hitl is True
            assert rows(deps) == []
    finally:
        deps.connection_factory.close()


def test_real_lock_lifespan_publishes_resolved_overrides_and_mcp_bootstrap_cannot_replace_them(tmp_path):
    home = tmp_path / 'home'
    deps = bootstrap({}, ['--home', str(home), '--embedding-mode', 'off'])
    lock = ServeLock(deps.config.home_dir, db_path=deps.config.db_path)
    lock.acquire()
    try:
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("INSERT INTO settings VALUES('feature_hitl','true','2026-11-06T12:00:00Z')")
        app = build_app(deps, lock=lock)
        assert deps.config.feature_hitl is True
        assert rows(deps) == []  # App construction is not an owning lifespan.
        with TestClient(app, client=('127.0.0.1', 50000)):
            before = policy(deps)
            assert set(before) == set(KEYS)
            assert {key: bool(row['value']) for key, row in before.items()} == live(deps)
            assert all(row['generation'] == 1 for row in before.values())
            other = bootstrap({'OKTO_NEXUS_FEATURE_HITL': 'false'},
                ['--home', str(home), '--embedding-mode', 'off'])
            try:
                assert policy(other) == before
                assert other.config.feature_hitl is False
            finally:
                other.connection_factory.close()
            assert policy(deps) == before
    finally:
        lock.release()
        deps.connection_factory.close()


def test_http_patch_reset_noop_and_reads_publish_only_effective_changes(tmp_path):
    with server(tmp_path / 'home') as (deps, _, client, _):
        original = policy(deps)
        defaults = live(deps)
        assert client.get('/api/v1/settings').status_code == 200
        assert client.patch('/api/v1/settings', json=defaults).status_code == 200
        assert client.patch('/api/v1/settings', json={'presence_ttl_seconds': 900}).status_code == 200
        assert policy(deps) == original
        changed = {key: not value for key, value in defaults.items()}
        assert client.patch('/api/v1/settings', json=changed).status_code == 200
        assert live(deps) == changed
        second = policy(deps)
        assert {key: bool(row['value']) for key, row in second.items()} == changed
        assert all(second[key]['generation'] == original[key]['generation'] + 1 for key in KEYS)
        assert client.patch('/api/v1/settings', json=changed).status_code == 200
        assert policy(deps) == second
        assert client.post('/api/v1/settings/reset').status_code == 200
        assert live(deps) == defaults
        third = policy(deps)
        assert all(third[key]['generation'] == second[key]['generation'] + 1 for key in KEYS)
        assert client.post('/api/v1/settings/reset').status_code == 200
        assert policy(deps) == third


@pytest.mark.parametrize('operation', ['patch', 'reset'])
@pytest.mark.parametrize('failure', ['after_stage', 'commit'])
def test_http_failure_rolls_back_settings_policy_and_live_config(tmp_path, monkeypatch, operation, failure):
    with server(tmp_path / 'home') as (deps, app, client, _):
        if operation == 'reset':
            assert client.patch('/api/v1/settings', json={key: not value for key, value in live(deps).items()}).status_code == 200
        before_policy, before_settings, before_live = rows(deps), rows(deps, 'settings'), live(deps)
        if failure == 'commit':
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute('CREATE TABLE policy_test_parent(id INTEGER PRIMARY KEY)')
                uow.connection.execute('CREATE TABLE policy_test_child(id INTEGER REFERENCES policy_test_parent(id) DEFERRABLE INITIALLY DEFERRED)')
        service = app.state.settings_service
        name = 'update' if operation == 'patch' else 'reset'
        original = getattr(service, name)

        def fail(uow, *args, **kwargs):
            result = original(uow, *args, **kwargs)
            assert live(deps) == before_live  # Still inside the uncommitted UoW.
            if failure == 'after_stage':
                raise OktoNexusError(ErrorCode.DB_ERROR, 'Injected failure after staged policy.', {})
            uow.connection.execute('INSERT INTO policy_test_child VALUES(999)')
            return result  # The deferred FK fails on the real SQLite COMMIT.

        monkeypatch.setattr(service, name, fail)
        response = (client.patch('/api/v1/settings', json={key: not value for key, value in before_live.items()})
                    if operation == 'patch' else client.post('/api/v1/settings/reset'))
        assert response.status_code >= 400
        assert rows(deps) == before_policy
        assert rows(deps, 'settings') == before_settings
        assert live(deps) == before_live
        assert client.get('/api/v1/settings').status_code == 200


@pytest.mark.parametrize('key', KEYS)
def test_restart_env_pin_and_reset_follow_effective_value_without_spurious_generation(tmp_path, key):
    home = tmp_path / 'home'
    with server(home) as (deps, _, client, _):
        default = getattr(deps.config, key)
        assert client.patch('/api/v1/settings', json={key: default}).status_code == 200
        first = policy(deps)
    env = {'OKTO_NEXUS_' + key.upper(): str(not default).lower()}
    with server(home, env=env) as (deps, _, client, _):
        second = policy(deps)
        assert bool(second[key]['value']) is not default
        assert second[key]['generation'] == first[key]['generation'] + 1
        other_key, = set(KEYS) - {key}
        assert second[other_key] == first[other_key]
        assert client.patch('/api/v1/settings', json={key: default}).status_code == 422
        assert client.post('/api/v1/settings/reset').status_code == 200
        assert getattr(deps.config, key) is not default
        assert policy(deps) == second
    with server(home, env=env) as (deps, _, _, _):
        assert policy(deps) == second


def test_released_serve_lock_cannot_publish_or_change_live_policy(tmp_path):
    with server(tmp_path / 'home') as (deps, _, client, lock):
        before_policy, before_settings, before_live = rows(deps), rows(deps, 'settings'), live(deps)
        lock.release()
        response = client.patch('/api/v1/settings', json={'feature_hitl': not before_live['feature_hitl']})
        assert response.status_code >= 400
        assert rows(deps) == before_policy
        assert rows(deps, 'settings') == before_settings
        assert live(deps) == before_live


@pytest.mark.parametrize('invalid', ['unowned', 'wrong_home', 'wrong_database'])
def test_lifespan_refuses_lock_without_exact_home_database_ownership(tmp_path, invalid):
    deps = bootstrap({}, ['--home', str(tmp_path / 'home'), '--embedding-mode', 'off'])
    lock = ServeLock(tmp_path / 'other' if invalid == 'wrong_home' else deps.config.home_dir,
        db_path=tmp_path / 'other.db' if invalid == 'wrong_database' else deps.config.db_path)
    if invalid != 'unowned':
        lock.acquire()
    try:
        app = build_app(deps, lock=lock)
        with pytest.raises(OktoNexusError) as caught:
            with TestClient(app, client=('127.0.0.1', 50000)):
                pytest.fail('An invalid owner entered the serving lifespan.')
        assert caught.value.code == ErrorCode.CONFIG_ERROR
        assert rows(deps) == []
    finally:
        lock.release()
        deps.connection_factory.close()


def test_reacquired_lock_generation_does_not_restore_old_app_policy_authority(tmp_path):
    with server(tmp_path / 'home') as (deps, _, client, lock):
        before_policy, before_settings, before_live = rows(deps), rows(deps, 'settings'), live(deps)
        generation = lock.generation
        lock.release()
        lock.acquire()
        assert lock.owned and lock.generation != generation
        response = client.patch('/api/v1/settings', json={'feature_hitl': not before_live['feature_hitl']})
        assert response.status_code >= 400
        assert rows(deps) == before_policy
        assert rows(deps, 'settings') == before_settings
        assert live(deps) == before_live
