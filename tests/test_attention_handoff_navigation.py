"""The existing handoff read can open a canonical record beyond its overview."""
import pytest

import test_attention_api as http_fixtures
from okto_nexus.adapters.inbound.http.app import ensure_operator_key
from okto_nexus.adapters.inbound.mcp.tools.handoff import build_service


BASE = '/api/v1/handoffs'
attention_env = http_fixtures.attention_env
device, snapshot = http_fixtures.device, http_fixtures.snapshot


def data(response):
    assert response.status_code == 200, response.text
    assert response.json()['ok'] is True
    return response.json()['data']


def completed(env):
    service = build_service(env.deps, register_approval_executor=False)
    handoff = service.handoff_create(workspace_id='attention-one', from_agent_id='operator',
        target={'strategy': 'direct', 'agent_id': 'attention-worker'}, visibility='eligible',
        payload='Original canonical work')
    identity = handoff['handoff_id']
    claim = service.handoff_claim(workspace_id='attention-one', handoff_id=identity, agent_id='attention-worker')
    service.handoff_complete(workspace_id='attention-one', handoff_id=identity, agent_id='attention-worker',
        claim_epoch=claim['claim_epoch'], result='Original canonical result')
    return identity


def test_exact_handoff_beyond_1000_overview_rows_is_read_without_side_effects(attention_env):
    env = attention_env
    identity = completed(env)
    env.clock.advance(10)
    with env.deps.connection_factory.unit_of_work() as uow:
        # The target above follows real create/claim/complete. Only the large
        # overview background below is synthetic metadata, without payloads.
        uow.connection.executemany(
            'INSERT INTO handoffs(handoff_id,workspace_id,from_agent_id,target,visibility,status,'
            'claimed_by,claim_epoch,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
            [(f'background-{index:04d}', 'attention-one', 'operator',
              '{"strategy":"direct","agent_id":"attention-worker"}', 'eligible', 'COMPLETED',
              'attention-worker', 1, env.clock.now_iso(), env.clock.now_iso()) for index in range(1001)])
    before = snapshot(env)
    overview = data(env.client.get(BASE, params={'workspace': 'attention-one', 'status': 'COMPLETED'}))
    assert len(overview['items']) == 1000
    assert identity not in {row['handoff_id'] for row in overview['items']}
    attention = data(env.client.get('/api/v1/attention', params={'kind': 'result_unseen', 'limit': 1}))
    assert attention['items'][0]['source_id'] == identity
    row, = data(env.client.get(BASE, params={'handoff_id': identity, 'workspace': 'attention-one',
        'status': 'COMPLETED', 'from_agent': 'operator', 'to_agent': 'attention-worker'}))['items']
    assert row['handoff_id'] == identity and row['workspace_id'] == 'attention-one'
    assert row['result'] == 'Original canonical result' and row['claim_epoch'] == 1
    assert snapshot(env) == before


def test_handoff_selector_composes_with_every_existing_filter_and_absence_stays_empty(attention_env):
    env = attention_env
    identity = completed(env)
    before = snapshot(env)
    for filters in ({'workspace': 'attention-two'}, {'status': 'OPEN'}, {'from_agent': 'other'},
                    {'to_agent': 'other'}, {'since': '2099-01-01T00:00:00Z'},
                    {'until': '2000-01-01T00:00:00Z'}):
        assert data(env.client.get(BASE, params={'handoff_id': identity, **filters})) == {'items': []}
    assert data(env.client.get(BASE, params={'handoff_id': 'missing-handoff'})) == {'items': []}
    assert data(env.client.get(BASE, params={'handoff_id': "' OR 1=1 --"})) == {'items': []}
    assert snapshot(env) == before


@pytest.mark.parametrize('value', ['', ' ', 'x' * 2049, 'bad\nreference', 'bad\x00reference'])
def test_invalid_handoff_selector_is_rejected_without_writes(attention_env, value):
    env = attention_env
    before = snapshot(env)
    response = env.client.get(BASE, params={'handoff_id': value})
    assert response.status_code == 422 and response.json()['error']['code'] == 'INVALID_PARAM'
    assert snapshot(env) == before


def test_duplicate_handoff_selector_is_not_silently_ambiguous(attention_env):
    env = attention_env
    response = env.client.get(BASE, params=[('handoff_id', 'first'), ('handoff_id', 'second')])
    assert response.status_code == 422 and response.json()['error']['code'] == 'INVALID_PARAM'


def test_selector_preserves_existing_observability_auth_and_key_revocation(attention_env):
    env = attention_env
    identity = completed(env)
    _, operator_key = ensure_operator_key(env.deps, env.app.state.auth)
    with env.deps.connection_factory.unit_of_work() as uow:
        worker_key = env.app.state.auth.issue_key(uow, agent_id='attention-worker')
    with device(env.app, client=('192.0.2.70', 51000)) as remote:
        assert remote.get(BASE).status_code == remote.get(BASE, params={'handoff_id': identity}).status_code == 401
        for key in (operator_key, worker_key):
            headers = {'x-api-key': key}
            # Existing observability accepts ordinary authenticated agent keys;
            # the exact selector neither grants new access nor adds an operator gate.
            full = data(remote.get(BASE, headers=headers))['items']
            selected, = data(remote.get(BASE, headers=headers, params={'handoff_id': identity}))['items']
            assert selected == next(row for row in full if row['handoff_id'] == identity)
        # Use the same canonical auth service that rotates dashboard keys and
        # invalidates its positive cache. General observability keeps that contract.
        with env.deps.connection_factory.unit_of_work() as uow:
            replacement = env.app.state.auth.issue_key(uow, agent_id='attention-worker')
        assert remote.get(BASE, headers={'x-api-key': worker_key}, params={'handoff_id': identity}).status_code == 401
        assert data(remote.get(BASE, headers={'x-api-key': replacement}, params={'handoff_id': identity}))['items'][0]['handoff_id'] == identity
