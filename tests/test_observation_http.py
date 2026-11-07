"""Production HTTP wiring and canonical/publish audience integration."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.bootstrap.dependencies import bootstrap


MANAGEMENT = '/api/v1/observations'
PUBLISH = '/v1/observations/activity'


@pytest.fixture
def http_obs(tmp_path, monkeypatch):
    from okto_nexus.bootstrap import embedded_inventory
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
                        lambda **_: SimpleNamespace(candidates=()))
    deps = bootstrap({}, ['--home', str(tmp_path), '--feature-observations', 'true',
                          '--feature-harness-integrations', 'false', '--embedding-mode', 'off'])
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    _, key = ensure_operator_key(deps, auth)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id='observed')
        agent_key = auth.issue_key(uow, agent_id='observed')
        deps.repos.agents.set_permissions(uow, agent_id='observed', preset_id=None, permissions={
            'observations': {'manage_self': True, 'publish': True}})
        deps.repos.workspaces.upsert(uow, workspace_id='obs-workspace')
    app = build_app(deps)
    client = TestClient(app, base_url='http://testserver')
    headers = {'Authorization': 'Bearer ' + key}
    source_response = client.post(MANAGEMENT + '/sources', headers=headers, json=dict(
        agent_id='observed', source_kind='custom', workspace_ids=['obs-workspace'], registration_ref='http-registration'))
    assert source_response.status_code == 200, source_response.text
    source = source_response.json()['data']['source']
    path = MANAGEMENT + '/sources/' + source['source_id']
    instance_response = client.post(path + '/instances', headers=headers, json=dict(
        expected_revision=source['revision'], workspace_id='obs-workspace', external_instance_ref='http-occupant'))
    assert instance_response.status_code == 200, instance_response.text
    instance = instance_response.json()['data']['instance']
    token_response = client.post(path + '/tokens', headers=headers, json=dict(
        expected_revision=source['revision'], instance_grants=[dict(
            observed_instance_id=instance['observed_instance_id'], generation=instance['generation'])]))
    assert token_response.status_code == 200, token_response.text
    token = token_response.json()['data']['token']
    payload = dict(schema_version=1, source_id=source['source_id'],
        observed_instance_id=instance['observed_instance_id'], generation=instance['generation'],
        sequence=1, state='blocked', evidence='inferred', observed_at=deps.clock.now_iso(),
        reason_code='external_input_required')
    yield SimpleNamespace(deps=deps, app=app, client=client, headers=headers, token=token,
        publish_headers={'Authorization': 'Bearer ' + token}, path=path, payload=payload,
        instance=instance, agent_key=agent_key)
    client.close()


def test_wired_management_publish_and_passive_historical_reads(http_obs):
    env = http_obs
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        before = [tuple(row) for row in uow.connection.execute('SELECT * FROM agents ORDER BY agent_id')]
    first = env.client.post(PUBLISH, headers=env.publish_headers, json=env.payload)
    assert first.status_code == 200, first.text
    repeated = env.client.post(PUBLISH, headers=env.publish_headers, json=env.payload)
    assert repeated.status_code == 200 and repeated.json()['data']['receipts'][0]['replayed']
    for path in (MANAGEMENT, MANAGEMENT + '/sources', env.path + '/instances', env.path + '/tokens'):
        response = env.client.get(path + '?limit=200', headers=env.headers)
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        assert env.token not in response.text and 'token_hash' not in response.text
    item = env.client.get(MANAGEMENT, headers=env.headers).json()['data']['items'][0]
    assert item['freshness'] == 'current' and item['activity_state'] == 'blocked'
    env.deps.config.feature_observations = False
    assert env.client.post(PUBLISH, headers=env.publish_headers, json=env.payload).status_code == 409
    item = env.client.get(MANAGEMENT, headers=env.headers).json()['data']['items'][0]
    assert item['freshness'] == 'unavailable' and item['activity_state'] == 'unknown'
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        assert [tuple(row) for row in uow.connection.execute('SELECT * FROM agents ORDER BY agent_id')] == before


@pytest.mark.parametrize('kind', ['duplicate', 'unknown', 'oversize', 'canonical-oversize', 'batch101', 'identity', 'bool-sequence', 'nan'])
def test_bounded_strict_http_errors_never_echo_input(http_obs, kind):
    env = http_obs
    data = dict(env.payload)
    secret = 'DO-NOT-ECHO-THIS-INPUT'
    if kind == 'unknown':
        data['prompt'] = secret
    elif kind == 'identity':
        data['agent_id'] = secret
    elif kind == 'bool-sequence':
        data['sequence'] = True
    elif kind == 'batch101':
        data = {'reports': [data] * 101}
    raw = json.dumps(data)
    if kind == 'canonical-oversize':
        from okto_nexus.domain.observations import parse_report
        data['current_completion_ref'] = chr(0x1F600) * 256
        for count in range(513):
            data['reason_text'] = '\x00' * count + chr(0x1F600) * (512 - count)
            raw = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
            canonical = json.dumps(parse_report(data).to_dict(), ensure_ascii=False, separators=(',', ':'))
            if len(raw.encode()) <= 4096 < len(canonical.encode()):
                break
        else:
            pytest.fail('No near-boundary regression payload was constructed')
    if kind == 'duplicate':
        raw = raw[:-1] + ',"state":"' + secret + '"}'
    elif kind == 'oversize':
        raw = raw + ' ' * 4096
    elif kind == 'nan':
        raw = raw[:-1] + ',"reason_text":NaN}'
    response = env.client.post(PUBLISH, headers=dict(env.publish_headers, **{'Content-Type': 'application/json'}), content=raw)
    assert response.status_code in (413, 422), response.text
    if kind == 'canonical-oversize':
        assert response.status_code == 413
    assert secret not in response.text and env.token not in response.text
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM observation_heads').fetchone()[0] == 0


def test_publish_bearer_cannot_reenter_management_or_canonical_audiences(http_obs):
    env = http_obs
    for path in (env.path + '/tokens', '/mcp', '/api/v1/messages', '/v1/executors/tickets'):
        response = env.client.post(path, headers=env.publish_headers, json={})
        assert response.status_code in (401, 403), response.text
    for token in (env.agent_key, env.headers['Authorization'].split()[1]):
        assert env.client.post(PUBLISH, headers={'Authorization': 'Bearer ' + token}, json=env.payload).status_code in (401, 403)


def test_http_storage_failure_never_acknowledges_or_leaks(http_obs, monkeypatch):
    env = http_obs
    def fail(*args, **kwargs):
        raise OSError('disk full /private/path ' + env.token)
    monkeypatch.setattr(env.app.state.observations.events, 'emit', fail)
    response = env.client.post(PUBLISH, headers=env.publish_headers, json=env.payload)
    assert response.status_code == 503 and response.json()['ok'] is False
    assert env.token not in response.text and '/private/path' not in response.text
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM observation_heads').fetchone()[0] == 0


def test_http_backpressure_returns_retry_after_before_storage(http_obs, monkeypatch):
    from contextlib import ExitStack
    env = http_obs
    guard = env.app.state.observations.ingress
    with ExitStack() as stack:
        for _ in range(32):
            stack.enter_context(guard.enter())
        response = env.client.post(PUBLISH, headers=env.publish_headers, json=env.payload)
    assert response.status_code == 503 and response.headers['Retry-After'] == '1'
    guard.available = 0
    monkeypatch.setattr(guard, 'timer', lambda: guard.updated)
    response = env.client.post(PUBLISH, headers=env.publish_headers, json=env.payload)
    assert response.status_code == 429 and int(response.headers['Retry-After']) >= 1
