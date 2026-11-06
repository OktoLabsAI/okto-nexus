"""HTTP policy recurrence over real owned lifespan and canonical pending work.

The existing native fixture admits work and commits its request through the
canonical services. Its remote provider qualification/dispatch peer is synthetic;
Server ownership, settings publication, attention reads and preferences are real.
"""
from datetime import timedelta
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent / 'execution_r4'))
import test_native_decisions as native_fixtures  # noqa: E402
import test_ns09 as authority_fixtures  # noqa: E402

from okto_nexus.adapters.inbound.http.lock import ServeLock  # noqa: E402
from okto_nexus.domain.attention import instant  # noqa: E402

opening = native_fixtures.opening
decision_state = native_fixtures.decision_state
KEYS = ('feature_harness_integrations', 'feature_hitl')


@pytest.fixture(autouse=True)
def owned_lifespan(monkeypatch):
    """Adapt fixture construction, keeping the real Server's owner predicate."""
    from okto_nexus.bootstrap import embedded_inventory
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
                        lambda **_: SimpleNamespace(candidates=()))
    bootstrap, build_app = authority_fixtures.bootstrap, authority_fixtures.build_app
    locks = []

    def editable_bootstrap(env, argv):
        # The fixture pins true for unrelated tests. Here use the same true
        # default so the real HTTP settings control remains operator-editable.
        argv = list(argv)
        offset = argv.index('--feature-harness-integrations')
        assert argv[offset + 1] == 'true'
        del argv[offset:offset + 2]
        return bootstrap(env, [*argv, '--embedding-mode', 'off'])

    def owning_app(deps):
        fixed = deps.clock.now_iso()
        monkeypatch.setattr(deps.clock, 'now_iso', lambda: fixed)
        lock = ServeLock(deps.config.home_dir, db_path=deps.config.db_path)
        lock.acquire()
        locks.append(lock)
        app = build_app(deps, lock=lock)
        app.state.policy_test_lock = lock
        app.state.policy_test_now = fixed
        return app

    monkeypatch.setattr(authority_fixtures, 'bootstrap', editable_bootstrap)
    monkeypatch.setattr(authority_fixtures, 'build_app', owning_app)
    try:
        yield
    finally:
        for lock in locks:
            lock.release()


def payload(response):
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['ok'], value
    return value['data']


def policy_rows(deps):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return {row['key']: dict(row) for row in uow.connection.execute('SELECT * FROM server_effective_policy')}


@pytest.mark.parametrize('key', KEYS)
def test_http_policy_same_clock_recurrence_has_new_ids_without_inherited_preferences(decision_state, key):
    deps, app, _ = decision_state
    assert app.state.policy_test_lock.owned
    fixed = app.state.policy_test_now
    # opening owns the live lifespan. This client only sends requests into the
    # same app; entering another TestClient lifespan would start a second owner.
    client = TestClient(app, client=('127.0.0.1', 50000))
    headers = {'x-api-key': app.state.test_agent_keys['operator']}
    filters = {'kind': 'execution_authority_blocking', 'state': 'all'}

    def patch(value):
        result = payload(client.patch('/api/v1/settings', headers=headers, json=value))
        assert result['applied'] == value

    def observed(state='all'):
        response = payload(client.get('/api/v1/attention', headers=headers, params={**filters, 'state': state}))
        assert instant(response['observed_at']) == instant(fixed)
        assert response['total'] == len(response['items'])
        assert response['counts']['action_required'] == len(response['items'])
        return response

    patch(dict.fromkeys(KEYS, True))
    assert observed()['items'] == []
    canonical = native_fixtures.snapshot(decision_state)
    initial_policy = policy_rows(deps)

    patch({key: False})
    first_policy = policy_rows(deps)
    assert first_policy[key]['generation'] == initial_policy[key]['generation'] + 1
    first = observed()['items']
    assert first
    # A normal queued turn has no required native-decision protocol. HITL
    # blocks its pending native request, not unrelated admitted execution.
    expected = {'execution_native_request'}
    if key == 'feature_harness_integrations':
        expected.add('execution_operation')
    assert {row['source_type'] for row in first} == expected
    saved_preferences = {}
    for item in first:
        endpoint = '/api/v1/attention/' + item['attention_id']
        marked = payload(client.post(endpoint + '/seen', headers=headers, json={
            'source_revision': item['source_revision'], 'preference_revision': 0, 'seen': True}))['item']
        assert marked['resolution'] == item['resolution'] == 'open'
        assert marked['active'] and marked['seen_state']['seen']
        snoozed = payload(client.post(endpoint + '/snooze', headers=headers, json={
            'source_revision': marked['source_revision'],
            'preference_revision': marked['seen_state']['revision'],
            'until': (instant(fixed) + timedelta(hours=1)).isoformat()}))['item']
        assert snoozed['resolution'] == 'open' and not snoozed['active']
        assert snoozed['seen_state']['seen'] and snoozed['seen_state']['snoozed']
        saved_preferences[item['attention_id']] = snoozed['seen_state']
    assert observed('active')['items'] == []
    retained = observed()['items']
    assert {row['attention_id']: row['seen_state'] for row in retained} == saved_preferences
    assert native_fixtures.snapshot(decision_state) == canonical

    patch({key: True})
    assert observed()['items'] == []
    patch({key: False})
    final_policy = policy_rows(deps)
    assert final_policy[key]['generation'] == first_policy[key]['generation'] + 2
    assert final_policy[key]['changed_at'] == first_policy[key]['changed_at']
    other, = set(KEYS) - {key}
    assert final_policy[other] == initial_policy[other]
    final = observed('active')['items']
    assert len(final) == len(first)
    assert {row['attention_id'] for row in first}.isdisjoint(row['attention_id'] for row in final)
    assert {row['source_revision'] for row in first}.isdisjoint(row['source_revision'] for row in final)
    assert all(row['seen_state'] == dict(seen=False, seen_at=None, snoozed=False,
        snoozed_until=None, revision=0) for row in final)
    assert native_fixtures.snapshot(decision_state) == canonical

    # Repeated PATCH and GET preserve the new episode and the old preferences.
    patch({key: False})
    assert policy_rows(deps) == final_policy
    assert observed('active')['items'] == final
    with deps.connection_factory.unit_of_work(write=False) as uow:
        old = [dict(row) for row in uow.connection.execute('SELECT * FROM attention_preferences')]
    assert {row['attention_id'] for row in old} == set(saved_preferences)
    assert all(row['seen_at'] and row['snoozed_until'] and row['revision'] == 2 for row in old)
    assert app.state.policy_test_lock.owned and deps.clock.now_iso() == fixed
