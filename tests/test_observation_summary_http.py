"""HTTP evidence for complete external activity summaries and exact inspection."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from okto_nexus.application.auth import AgentKeyAuthService
from test_observation_http import MANAGEMENT, PUBLISH, http_obs as http_obs_fixture


http_obs = http_obs_fixture


def data(env, path, *, headers=None):
    response = env.client.get(path, headers=env.headers if headers is None else headers)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert env.token not in response.text and 'token_hash' not in response.text
    assert 'api_key_hash' not in response.text and 'publisher_token_id' not in response.text
    return response.json()['data']


def detail_path(env):
    return MANAGEMENT + '/instances/' + env.instance['observed_instance_id']


def publish(env, **changes):
    response = env.client.post(PUBLISH, headers=env.publish_headers, json=dict(env.payload, **changes))
    assert response.status_code == 200, response.text
    return response.json()['data']['receipts'][0]


def snapshot(env):
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        names = [row[0] for row in uow.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name: sorted((tuple(row) for row in uow.connection.execute(
            'SELECT * FROM "' + name + '"')), key=repr) for name in names}


def foreign_source(env):
    auth = AgentKeyAuthService(env.deps.repos.agents, env.deps.clock)
    with env.deps.connection_factory.unit_of_work() as uow:
        env.deps.repos.agents.upsert(uow, agent_id='foreign')
        auth.issue_key(uow, agent_id='foreign')
        env.deps.repos.agents.set_permissions(uow, agent_id='foreign', preset_id=None, permissions={
            'observations': {'manage_self': True, 'publish': True}})
        env.deps.repos.workspaces.upsert(uow, workspace_id='foreign-workspace')
    response = env.client.post(MANAGEMENT + '/sources', headers=env.headers, json=dict(
        agent_id='foreign', source_kind='hook', workspace_ids=['foreign-workspace'], registration_ref='foreign'))
    assert response.status_code == 200, response.text
    source = response.json()['data']['source']
    response = env.client.post(MANAGEMENT + '/sources/' + source['source_id'] + '/instances',
        headers=env.headers, json=dict(expected_revision=source['revision'],
            workspace_id='foreign-workspace', external_instance_ref='same-name-is-not-identity'))
    assert response.status_code == 200, response.text
    return source, response.json()['data']['instance']


@pytest.mark.parametrize('endpoint', ['summary', 'detail'])
@pytest.mark.parametrize('credential', ['missing', 'publisher', 'invalid'])
def test_read_endpoints_require_canonical_read_authority(http_obs, endpoint, credential):
    env = http_obs
    path = MANAGEMENT + '/summary' if endpoint == 'summary' else detail_path(env)
    headers = {} if credential == 'missing' else env.publish_headers if credential == 'publisher' else {
        'Authorization': 'Bearer invalid-qualification-token'}
    response = env.client.get(path, headers=headers)
    assert response.status_code in (401, 403)
    assert env.token not in response.text and 'http-occupant' not in response.text


def test_summary_and_exact_inspection_share_current_facts_without_writes(http_obs):
    env = http_obs
    receipt = publish(env)
    before = snapshot(env)
    summary = data(env, MANAGEMENT + '/summary')
    detail = data(env, detail_path(env))
    item = detail['item']
    assert summary['version'] == 1 and summary['total_instances'] == 1
    assert summary['activity'] == dict(working=0, idle=0, blocked=1, unknown=0)
    assert summary['freshness'] == dict(current=1, stale=0, unknown=0, unavailable=0)
    assert summary['agents'] == [dict(agent_id='observed', total_instances=1,
        activity=summary['activity'], freshness=summary['freshness'])]
    for key in ('source_id', 'observed_instance_id', 'generation'):
        assert item[key] == env.payload[key]
    assert item['agent_id'] == 'observed' and item['workspace_id'] == 'obs-workspace'
    assert item['activity_state'] == 'blocked' and item['freshness'] == 'current'
    assert item['last_report']['valid_until'] == receipt['valid_until']
    assert item['observational_only'] is True and item['canonical_session_ref'] is None
    for value in (summary, detail):
        assert value['feature_enabled'] is True
        assert 0 < value['refresh_after_seconds'] <= 15
        assert value['next_refresh_at'] > value['observed_at']
    assert snapshot(env) == before


def test_complete_summary_is_independent_of_bounded_instance_page(http_obs):
    env = http_obs
    service = env.app.state.observations
    with env.deps.connection_factory.unit_of_work() as uow:
        source = service.repo.get_source(uow, source_id=env.payload['source_id'])
        for index in range(205):
            service.repo.create_instance(uow, source_id=source['source_id'], expected_revision=source['revision'],
                workspace_id='obs-workspace', external_instance_ref=f'bounded-summary-{index}',
                now=env.deps.clock.now_iso(), instance_limit=4096)
    publish(env, state='working')
    page = data(env, MANAGEMENT + '?limit=200')
    summary = data(env, MANAGEMENT + '/summary?workspace_id=obs-workspace')
    assert len(page['items']) == 200 and page['next_after'] is not None
    assert summary['total_instances'] == 206
    assert summary['activity'] == dict(working=1, idle=0, blocked=0, unknown=205)
    assert summary['freshness'] == dict(current=1, stale=0, unknown=205, unavailable=0)
    assert summary['agents'][0]['total_instances'] == 206


def test_self_scope_cannot_inspect_or_count_another_agent(http_obs):
    env = http_obs
    foreign, instance = foreign_source(env)
    headers = {'Authorization': 'Bearer ' + env.agent_key}
    own = data(env, MANAGEMENT + '/summary', headers=headers)
    assert own['total_instances'] == 1 and [a['agent_id'] for a in own['agents']] == ['observed']
    assert data(env, detail_path(env), headers=headers)['item']['agent_id'] == 'observed'
    response = env.client.get(MANAGEMENT + '/instances/' + instance['observed_instance_id'], headers=headers)
    assert response.status_code == 404
    assert 'foreign-workspace' not in response.text and 'same-name-is-not-identity' not in response.text
    assert env.client.get(MANAGEMENT + '/summary?agent_id=foreign', headers=headers).status_code == 403
    assert env.client.get(MANAGEMENT + '/summary?source_id=' + foreign['source_id'], headers=headers).status_code == 404
    assert data(env, MANAGEMENT + '/summary?workspace_id=foreign-workspace', headers=headers)['total_instances'] == 0


def test_operator_filters_use_the_same_complete_relation(http_obs):
    env = http_obs
    source, _ = foreign_source(env)
    publish(env)
    assert data(env, MANAGEMENT + '/summary')['total_instances'] == 2
    for query in ('agent_id=foreign', 'workspace_id=foreign-workspace', 'source_id=' + source['source_id']):
        value = data(env, MANAGEMENT + '/summary?' + query)
        assert value['total_instances'] == 1
        assert [row['agent_id'] for row in value['agents']] == ['foreign']
        assert value['activity']['unknown'] == 1 and value['freshness']['unknown'] == 1
    assert data(env, MANAGEMENT + '/summary?agent_id=foreign&workspace_id=obs-workspace')['total_instances'] == 0


def test_expiry_changes_projection_without_declaring_idle_or_writing(http_obs):
    env = http_obs
    publish(env, state='working', valid_for_seconds=30)
    future = datetime.now(timezone.utc) + timedelta(seconds=35)
    env.app.state.observations.clock = SimpleNamespace(now_iso=lambda: future.isoformat())
    before = snapshot(env)
    summary = data(env, MANAGEMENT + '/summary')
    detail = data(env, detail_path(env))['item']
    assert summary['activity'] == dict(working=0, idle=0, blocked=0, unknown=1)
    assert summary['freshness'] == dict(current=0, stale=1, unknown=0, unavailable=0)
    assert detail['activity_state'] == 'unknown' and detail['last_report']['state'] == 'working'
    assert snapshot(env) == before


@pytest.mark.parametrize('mode', ['feature', 'source', 'token', 'agent'])
def test_disabled_or_revoked_observation_is_historical_not_current(http_obs, mode):
    env = http_obs
    publish(env, state='idle', current_completion_ref='finished-observing')
    if mode == 'feature':
        env.deps.config.feature_observations = False
    elif mode == 'source':
        response = env.client.post(env.path + '/revoke', headers=env.headers, json={'expected_revision': 1})
        assert response.status_code == 200, response.text
    elif mode == 'token':
        tokens = data(env, env.path + '/tokens')['items']
        response = env.client.post(env.path + '/tokens/' + tokens[0]['token_id'] + '/revoke', headers=env.headers)
        assert response.status_code == 200, response.text
    else:
        with env.deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='observed'")
    before = snapshot(env)
    summary = data(env, MANAGEMENT + '/summary')
    detail = data(env, detail_path(env))['item']
    assert summary['activity'] == dict(working=0, idle=0, blocked=0, unknown=1)
    assert summary['freshness'] == dict(current=0, stale=0, unknown=0, unavailable=1)
    assert detail['activity_state'] == 'unknown' and detail['freshness'] == 'unavailable'
    assert detail['last_report']['current_completion_ref'] == 'finished-observing'
    assert snapshot(env) == before


def test_rotation_cannot_return_old_occupant_as_current(http_obs):
    env = http_obs
    publish(env)
    response = env.client.post(env.path + '/instances/' + env.instance['observed_instance_id'] + '/rotate',
        headers=env.headers, json=dict(expected_revision=1, expected_generation=env.instance['generation']))
    assert response.status_code == 200, response.text
    item = data(env, detail_path(env))['item']
    assert item['generation'] > env.instance['generation']
    assert item['activity_state'] == 'unknown' and item['last_report'] is None
    assert data(env, MANAGEMENT + '/summary')['activity']['blocked'] == 0


@pytest.mark.parametrize('query', ['limit=1', 'after=x', 'agent_id=a&agent_id=b', 'unknown=1'])
def test_summary_rejects_pagination_or_ambiguous_filters(http_obs, query):
    response = http_obs.client.get(MANAGEMENT + '/summary?' + query, headers=http_obs.headers)
    assert response.status_code == 422, response.text


def test_detail_rejects_query_and_unknown_reference(http_obs):
    env = http_obs
    assert env.client.get(detail_path(env) + '?agent_id=observed', headers=env.headers).status_code == 422
    assert env.client.get(MANAGEMENT + '/instances/obs_inst_missing', headers=env.headers).status_code == 404


@pytest.mark.parametrize('endpoint', ['summary', 'detail'])
def test_read_storage_failure_is_not_an_empty_summary_or_leaked_error(http_obs, monkeypatch, endpoint):
    env = http_obs
    def unavailable(*args, **kwargs):
        raise OSError('private-database-location ' + env.token)
    monkeypatch.setattr(env.app.state.observations.repo,
                        'all_current' if endpoint == 'summary' else 'get_current', unavailable)
    response = env.client.get(MANAGEMENT + '/summary' if endpoint == 'summary' else detail_path(env), headers=env.headers)
    assert response.status_code == 503
    assert response.json()['ok'] is False
    assert env.token not in response.text and 'private-database-location' not in response.text


def test_repeated_completion_stays_observational_and_text_stays_data(http_obs):
    env = http_obs
    malicious = '<img src=x onerror=alert(1)> javascript:prompt(1)'
    publish(env, state='idle', current_completion_ref='same-finish', reason_text=malicious)
    before = snapshot(env)
    item = data(env, detail_path(env))['item']
    assert item['last_report']['reason_text'] == malicious
    assert item['observational_only'] is True
    assert json.loads(json.dumps(item)) == item
    assert snapshot(env) == before
    publish(env, sequence=2, state='idle', current_completion_ref='same-finish', reason_text=malicious)
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM events WHERE type='observation.completion'").fetchone()[0] == 1
