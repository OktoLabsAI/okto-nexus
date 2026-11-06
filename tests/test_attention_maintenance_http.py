"""Canonical maintenance inspection by reference, including retained history."""
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent / 'execution_r4'))
import test_canonical_artifact_maintenance as maintenance_fixtures  # noqa: E402

from okto_nexus.adapters.inbound.http.operator_auth import COOKIE
from okto_nexus.application.auth import AgentKeyAuthService

local_setup = maintenance_fixtures.local_setup
connected_local = maintenance_fixtures.connected_local
qualified_contract = maintenance_fixtures.qualified_contract
qualified_bridge = maintenance_fixtures.qualified_bridge
runtime = maintenance_fixtures.runtime

BASE = '/api/v1/harness/artifacts'


def data(response):
    assert response.status_code == 200, response.text
    assert response.json()['ok'] is True
    return response.json()['data']


def mutation_snapshot(deps):
    # Authentication/authorization audits are part of the existing route and
    # may be recorded even for rejected input. The selector cannot mutate work,
    # artifacts, cleanup receipts, reservations or quota settings.
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return {table: sorted((tuple(row) for row in uow.connection.execute('SELECT * FROM ' + table)), key=repr)
            for table in ('runtime_results', 'runtime_result_maintenance', 'runtime_artifact_settings',
                'artifacts', 'execution_operations', 'delivery_outbox')}


def quota_record(setup):
    _, _, client, headers, *_ = setup
    result = data(client.post(BASE, headers=headers['operator'], json={
        'action': 'quota', 'quota_bytes': 1048576,
        'idempotency_key': 'canonical-quota', 'reason': 'Synthetic approved capacity'}))
    assert result['state'] == 'DONE'
    return result['maintenance_id']


def test_selected_canonical_cleanup_beyond_first_100_remains_readable_after_done(runtime, monkeypatch):
    deps, _, client, headers, *_ = runtime[0]
    _, blocked = maintenance_fixtures.rejected_artifact(runtime, monkeypatch)
    body = dict(action='cleanup', result_id=blocked['result_id'],
        idempotency_key='canonical-selected-cleanup', reason='Synthetic cleanup recovery')
    discard = deps.repos.artifact_store.discard_unpublished
    calls = []

    def lost_cleanup_result(**kwargs):
        calls.append(None)
        discard(**kwargs)
        raise OSError('synthetic lost cleanup response')

    with monkeypatch.context() as cut:
        cut.setattr(deps.repos.artifact_store, 'discard_unpublished', lost_cleanup_result)
        lost = client.post(BASE, headers=headers['operator'], json=body)
        assert lost.status_code == 409, lost.text
        maintenance_id = lost.json()['error']['details']['maintenance_id']
        assert len(calls) == 1
        with deps.connection_factory.unit_of_work() as uow:
            selected = dict(uow.connection.execute(
                'SELECT * FROM runtime_result_maintenance WHERE maintenance_id=?', (maintenance_id,)).fetchone())
            assert selected['status'] == 'PENDING' and selected['attention_failure_at']
            # Only the pagination background is synthetic retained metadata.
            # The selected receipt above was emitted by the actual cleanup.
            for index in range(100):
                older = dict(selected, maintenance_id=f'maintenance_older_{index:03d}',
                    idempotency_key=f'older-{index}', action='quota', result_id=None,
                    artifact_id=None, artifact_generation=None, workspace_id=None, agent_id=None,
                    reserved_bytes=0, created_at='2000-01-01T00:00:00.000000Z',
                    updated_at='2000-01-01T00:00:00.000000Z', attention_failure_at=None,
                    attention_failure_code=None)
                uow.connection.execute('INSERT INTO runtime_result_maintenance(' + ','.join(older) +
                    ') VALUES (' + ','.join('?' for _ in older) + ')', tuple(older.values()))
        before = mutation_snapshot(deps)
        listing = data(client.post(BASE, headers=headers['operator'], json={}))
        assert len(listing['pending_maintenance']) == 100
        assert maintenance_id not in {row['maintenance_id'] for row in listing['pending_maintenance']}
        selected_view = data(client.post(BASE, headers=headers['operator'], json={
            'action': 'inspect', 'maintenance_id': maintenance_id}))
        assert selected_view['maintenance']['maintenance_id'] == maintenance_id
        assert selected_view['maintenance']['status'] == 'PENDING'
        assert [row['maintenance_id'] for row in selected_view['pending_maintenance']] == [maintenance_id]
        assert [row['result_id'] for row in selected_view['results']] == [blocked['result_id']]
        assert mutation_snapshot(deps) == before and len(calls) == 1
    completed = data(client.post(BASE, headers=headers['operator'], json=body))
    assert completed['state'] == 'DONE' and completed['maintenance_id'] == maintenance_id
    before = mutation_snapshot(deps)
    history = data(client.post(BASE, headers=headers['operator'], json={'maintenance_id': maintenance_id}))
    assert history['maintenance']['status'] == 'DONE'
    assert history['maintenance']['maintenance_id'] == maintenance_id
    assert history['pending_maintenance'] == []
    assert len(history['results']) == 1 and history['results'][0]['artifact_reserved_bytes'] == 0
    assert mutation_snapshot(deps) == before
    encoded = json.dumps(history)
    assert str(deps.repos.artifact_store.root) not in encoded and 'L' * 100 not in encoded
    assert all(name not in history['maintenance'] for name in ('response', 'artifact_id', 'storage_path', 'output_text'))
    assert all(name not in history['results'][0] for name in ('response', 'storage_path', 'output_text', 'publication_response'))


def test_invalid_selector_and_cleanup_combinations_never_mutate_or_discard(local_setup, monkeypatch):
    deps, _, client, headers, *_ = local_setup
    maintenance_id = quota_record(local_setup)
    before = mutation_snapshot(deps)
    calls = []
    monkeypatch.setattr(deps.repos.artifact_store, 'discard_unpublished', lambda **kwargs: calls.append(kwargs))
    invalid = [{'maintenance_id': value} for value in (True, 0, [], {}, '', 'x' * 129)]
    invalid += [
        {'action': 'cleanup', 'maintenance_id': maintenance_id, 'result_id': 'some-result',
            'idempotency_key': 'must-not-create', 'reason': 'Synthetic refusal'},
        {'action': 'quota', 'maintenance_id': maintenance_id, 'quota_bytes': 262144,
            'idempotency_key': 'must-not-create', 'reason': 'Synthetic refusal'},
        {'action': 'retry', 'maintenance_id': maintenance_id, 'result_id': 'some-result',
            'idempotency_key': 'must-not-create', 'reason': 'Synthetic refusal'},
        {'maintenance_id': maintenance_id, 'result_id': 'some-result'},
        {'maintenance_id': maintenance_id, 'quota_bytes': 262144},
        {'maintenance_id': maintenance_id, 'idempotency_key': 'must-not-create'},
        {'maintenance_id': maintenance_id, 'reason': 'Synthetic refusal'},
        {'maintenance_id': maintenance_id, 'output_text': 'private-parameter-marker'},
    ]
    for body in invalid:
        response = client.post(BASE, headers=headers['operator'], json=body)
        assert response.status_code == 422, (body, response.text)
        assert response.json()['error']['code'] == 'VALIDATION_ERROR'
        assert mutation_snapshot(deps) == before and not calls
    missing = client.post(BASE, headers=headers['operator'], json={'maintenance_id': 'missing-maintenance'})
    assert missing.status_code == 404 and missing.json()['error']['code'] == 'NOT_FOUND'
    assert mutation_snapshot(deps) == before and not calls


def test_selector_preserves_agent_refusal_key_revocation_and_cookie_csrf(local_setup):
    deps, app, client, headers, *_ = local_setup
    maintenance_id = quota_record(local_setup)
    body = {'action': 'inspect', 'maintenance_id': maintenance_id}
    assert data(client.post(BASE, headers=headers['operator'], json=body))['maintenance']['status'] == 'DONE'
    before = mutation_snapshot(deps)
    refused = client.post(BASE, headers=headers['subject'], json=body)
    assert refused.status_code == 403, refused.text
    assert mutation_snapshot(deps) == before
    # Warm the key path, rotate through an independent auth service, then use
    # the old key again. The selector cannot turn cached auth into authority.
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    with deps.connection_factory.unit_of_work() as uow:
        replacement = auth.issue_key(uow, agent_id='operator')
    rejected = client.post(BASE, headers=headers['operator'], json=body)
    assert rejected.status_code in (401, 403), rejected.text
    assert data(client.post(BASE, headers={'x-api-key': replacement}, json=body))['maintenance']['maintenance_id'] == maintenance_id
    account = {'username': 'maintenance-operator', 'password': 'synthetic-maintenance-password'}
    app.state.operator_auth.configure(**account, local=True)
    remote = TestClient(app, client=('192.0.2.40', 51000))
    try:
        remote.cookies.set(COOKIE, app.state.operator_auth.login(**account))
        valid_headers = {'x-nexus-ui': '1', 'Origin': 'http://testserver'}
        for csrf in ({}, {'x-nexus-ui': '1', 'Origin': 'https://foreign.example'},
                {'x-nexus-ui': '1', 'Sec-Fetch-Site': 'cross-site'}):
            response = remote.post(BASE, json=body, headers=csrf)
            assert response.status_code == 403, response.text
        valid = data(remote.post(BASE, json=body, headers=valid_headers))
        assert valid['maintenance']['maintenance_id'] == maintenance_id
        assert remote.post(BASE, json=body, headers={**valid_headers, **headers['subject']}).status_code == 403
    finally:
        remote.close()
    assert mutation_snapshot(deps) == before


def test_cleanup_inspection_survives_feature_off_and_absent_dispatcher(runtime, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.tools import harness

    deps, _, client, headers, *_ = runtime[0]
    _, blocked = maintenance_fixtures.rejected_artifact(runtime, monkeypatch)
    body = dict(action='cleanup', result_id=blocked['result_id'],
        idempotency_key='cleanup-inspection-without-owner', reason='Synthetic cleanup recovery')
    discard = deps.repos.artifact_store.discard_unpublished
    calls = []

    def lost_cleanup_result(**kwargs):
        calls.append(None)
        discard(**kwargs)
        raise OSError('synthetic lost cleanup response')

    with monkeypatch.context() as cut:
        cut.setattr(deps.repos.artifact_store, 'discard_unpublished', lost_cleanup_result)
        response = client.post(BASE, headers=headers['operator'], json=body)
        assert response.status_code == 409, response.text
        maintenance_id = response.json()['error']['details']['maintenance_id']
    inspect = {'action': 'inspect', 'maintenance_id': maintenance_id}
    proxies = []

    def unexpected_proxy(*args, **kwargs):
        proxies.append(None)
        raise AssertionError('Inspection must read locally without an owner proxy')

    with monkeypatch.context() as offline:
        offline.setattr(deps.config, 'feature_harness_integrations', False)
        offline.setattr(deps, 'runtime_dispatcher', None)
        offline.setattr(harness, 'call_runtime_owner', unexpected_proxy)
        offline.setattr(deps.repos.artifact_store, 'discard_unpublished', lost_cleanup_result)
        before = mutation_snapshot(deps)
        pending = data(client.post(BASE, headers=headers['operator'], json=inspect))
        assert pending['maintenance']['maintenance_id'] == maintenance_id
        assert pending['maintenance']['status'] == 'PENDING'
        assert [row['maintenance_id'] for row in pending['pending_maintenance']] == [maintenance_id]
        assert client.post(BASE, headers=headers['subject'], json=inspect).status_code == 403
        for mutation in (body, dict(body, action='retry'), dict(action='quota', quota_bytes=1048576,
                idempotency_key='offline-quota', reason='Synthetic refusal')):
            refused = client.post(BASE, headers=headers['operator'], json=mutation)
            assert refused.status_code == 403, refused.text
        auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
        with deps.connection_factory.unit_of_work() as uow:
            replacement = auth.issue_key(uow, agent_id='operator')
        assert client.post(BASE, headers=headers['operator'], json=inspect).status_code == 403
        replacement_headers = {'x-api-key': replacement}
        assert data(client.post(BASE, headers=replacement_headers, json=inspect))['maintenance']['status'] == 'PENDING'
        assert mutation_snapshot(deps) == before and calls == [None] and not proxies

    completed = data(client.post(BASE, headers=replacement_headers, json=body))
    assert completed['state'] == 'DONE' and completed['maintenance_id'] == maintenance_id
    with monkeypatch.context() as offline:
        offline.setattr(deps.config, 'feature_harness_integrations', False)
        offline.setattr(deps, 'runtime_dispatcher', None)
        offline.setattr(harness, 'call_runtime_owner', unexpected_proxy)
        before = mutation_snapshot(deps)
        history = data(client.post(BASE, headers=replacement_headers, json=inspect))
        assert history['maintenance']['maintenance_id'] == maintenance_id
        assert history['maintenance']['status'] == 'DONE' and history['pending_maintenance'] == []
        assert mutation_snapshot(deps) == before and not proxies
        encoded = json.dumps(history)
        assert str(deps.repos.artifact_store.root) not in encoded and 'L' * 100 not in encoded
        assert all(name not in history['maintenance'] for name in ('response', 'storage_path', 'output_text'))
        assert all(name not in row for row in history['results']
            for name in ('response', 'storage_path', 'output_text', 'publication_response'))
