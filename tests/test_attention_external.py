"""External attention observes metadata without granting productive authority."""
from copy import deepcopy
import json

import pytest

from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries
from okto_nexus.application.attention import AttentionService
from okto_nexus.application.database_reset import clear_operational_history
from okto_nexus.errors import OktoNexusError
from test_observation_service import OPERATOR, advance, obs, publish, snapshot  # noqa: F401


@pytest.fixture
def external(obs):  # noqa: F811 -- imported pytest fixture, injected by name
    obs.config.feature_attention = True
    obs.attention = AttentionService(factory=obs.factory, access=obs.service.access,
        queries=SqliteAttentionQueries(), clock=obs.clock, config=obs.config)
    return obs


def view(env, **filters):
    return env.attention.read(context=OPERATOR, filters=filters)


def seen(env, item):
    return env.attention.mark_seen(context=OPERATOR, attention_id=item['attention_id'],
        source_revision=item['source_revision'], preference_revision=item['seen_state']['revision'])['item']


def new_token(env):
    value = env.service.issue_token(context=OPERATOR, source_id=env.source['source_id'], body=dict(
        expected_revision=env.source['revision'], instance_grants=[dict(
            observed_instance_id=env.instance['observed_instance_id'], generation=env.instance['generation'])]))
    env.token, env.credential = value['token'], value['credential']


def test_blocked_is_observational_navigation_only_and_read_does_not_mutate(external):
    env = external
    publish(env, state='blocked', evidence='inferred', reason_code='external_input_required',
            reason_text='<script>synthetic()</script>')
    before = snapshot(env, auxiliary=True)
    result = view(env, kind='external_blocked')
    assert result['total'] == 1 and result['counts']['watch'] == 1
    item = result['items'][0]
    assert item['category'] == 'watch'
    assert item['allowed_actions'] == ['inspect_external_observation']
    assert item['source_type'] == 'external_observation'
    assert item['session_id'] is item['operation_id'] is None
    assert item['external_observation'] == env.service.read(context=OPERATOR)['items'][0]
    assert item['external_observation']['last_report']['reason_text'] == '<script>synthetic()</script>'
    assert env.token not in json.dumps(result)
    assert 'publisher_token_id' not in json.dumps(result)
    assert snapshot(env, auxiliary=True) == before


def test_continuous_blocked_heartbeat_retains_episode_and_seen(external):
    env = external
    publish(env, state='blocked')
    first = view(env, kind='external_blocked')['items'][0]
    seen(env, first)
    advance(env, 15)
    publish(env, sequence=2, state='blocked')
    second = view(env, kind='external_blocked')['items'][0]
    assert second['attention_id'] == first['attention_id']
    assert second['first_detected_at'] == first['first_detected_at']
    assert second['seen_state']['seen'] is True and second['active'] is True
    assert second['source_revision'] != first['source_revision']
    with pytest.raises(OktoNexusError, match='CONFLICT'):
        seen(env, first)


@pytest.mark.parametrize('gap', [0, 90, 120])
def test_blocked_recurrence_and_unobserved_expiration_do_not_inherit_seen(external, gap):
    env = external
    publish(env, state='blocked')
    first = view(env, kind='external_blocked')['items'][0]
    seen(env, first)
    if gap:
        advance(env, gap)
    else:
        publish(env, sequence=2, state='working')
    publish(env, sequence=3, state='blocked')
    current = view(env, kind='external_blocked')['items'][0]
    assert current['attention_id'] != first['attention_id']
    assert current['seen_state']['seen'] is False


@pytest.mark.parametrize('seconds, same_episode', [(89.999999, True), (90, False), (90.000001, False)])
def test_blocked_continuity_uses_exact_microsecond_expiration(external, seconds, same_episode):
    env = external
    publish(env, state='blocked')
    first = view(env, kind='external_blocked')['items'][0]
    advance(env, seconds)
    publish(env, sequence=2, state='blocked')
    current = view(env, kind='external_blocked')['items'][0]
    assert (current['attention_id'] == first['attention_id']) is same_episode


def test_revoked_publisher_then_new_token_starts_new_blocked_episode(external):
    env = external
    publish(env, state='blocked')
    first = view(env, kind='external_blocked')['items'][0]
    seen(env, first)
    env.service.revoke_token(context=OPERATOR, source_id=env.source['source_id'], token_id=env.credential['token_id'])
    assert view(env, kind='external_blocked')['items'] == []
    new_token(env)
    publish(env, sequence=2, state='blocked')
    assert view(env, kind='external_blocked')['items'][0]['attention_id'] != first['attention_id']


def test_source_revision_after_disable_and_enable_does_not_reuse_episode(external):
    env = external
    publish(env, state='blocked')
    first = view(env, kind='external_blocked')['items'][0]
    seen(env, first)
    for enabled in (False, True):
        env.source = env.service.update_source(context=OPERATOR, source_id=env.source['source_id'], body=dict(
            expected_revision=env.source['revision'], enabled=enabled))['source']
    new_token(env)
    publish(env, sequence=2, state='blocked')
    assert view(env, kind='external_blocked')['items'][0]['attention_id'] != first['attention_id']


def test_expiration_is_passive_and_stale_recurs_after_recovery(external):
    env = external
    publish(env, state='blocked', valid_for_seconds=30)
    before = snapshot(env, auxiliary=True)
    advance(env, 30)
    assert view(env, kind='external_blocked')['total'] == 0
    stale = view(env, kind='external_observation_stale')['items'][0]
    assert stale['freshness'] == 'stale'
    assert stale['external_observation']['activity_state'] == 'unknown'
    assert snapshot(env, auxiliary=True) == before
    seen(env, stale)
    assert view(env, kind='external_observation_stale')['items'][0]['active']
    publish(env, sequence=2, state='working', valid_for_seconds=30)
    assert view(env, kind='external_observation_stale')['total'] == 0
    advance(env, 30)
    next_stale = view(env, kind='external_observation_stale')['items'][0]
    assert next_stale['attention_id'] != stale['attention_id']
    assert not next_stale['seen_state']['seen']


def test_missing_report_and_idle_without_completion_do_not_invent_occurrences(external):
    assert view(external)['total'] == 0
    advance(external, 3600)
    assert view(external)['total'] == 0
    new_token(external)
    publish(external, state='idle')
    assert view(external)['total'] == 0


def test_multiple_completions_same_clock_are_retained_and_seen_independently(external):
    env = external
    publish(env, state='idle', current_completion_ref='one')
    publish(env, sequence=2, state='idle', current_completion_ref='one')
    publish(env, sequence=3, state='working')
    publish(env, sequence=4, state='idle', current_completion_ref='two')
    values = view(env, kind='external_completion_unseen')['items']
    assert len(values) == 2
    assert len({item['attention_id'] for item in values}) == 2
    assert {item['external_observation']['last_report']['sequence'] for item in values} == {1, 4}
    assert {item['external_observation']['last_report']['current_completion_ref'] for item in values} == {'one', 'two'}
    assert all(item['resolution'] == 'resolved' and item['active'] for item in values)
    seen(env, values[0])
    assert view(env, kind='external_completion_unseen')['total'] == 1
    assert view(env, kind='external_completion_unseen', state='all')['total'] == 2
    publish(env, sequence=5, state='working')
    assert view(env, kind='external_completion_unseen')['total'] == 1


def test_completion_stays_historical_unseen_after_ttl_without_becoming_task_success(external):
    env = external
    publish(env, state='idle', current_completion_ref='observed-end')
    before = snapshot(env)
    advance(env, 100)
    value = view(env, kind='external_completion_unseen')['items'][0]
    assert value['freshness'] == 'stale' and value['resolution'] == 'resolved'
    assert value['external_observation']['activity_state'] == 'unknown'
    assert value['operation_id'] is value['message_id'] is value['result_id'] is None
    assert snapshot(env) == before


def test_old_completion_does_not_reactivate_after_token_revoke_and_fresh_report(external):
    env = external
    publish(env, state='idle', current_completion_ref='one')
    original = view(env, kind='external_completion_unseen')['items'][0]
    old_token = env.credential['token_id']
    env.service.revoke_token(context=OPERATOR, source_id=env.source['source_id'], token_id=old_token)
    new_token(env)
    publish(env, sequence=2, state='working')
    assert view(env, kind='external_completion_unseen')['total'] == 0
    history = view(env, kind='external_completion_unseen', state='all')['items'][0]
    assert history['attention_id'] == original['attention_id']
    assert history['freshness'] == 'unavailable' and not history['active']
    with env.factory.unit_of_work() as uow:
        env.repos.observations.prune(uow, now=env.clock.now_iso())
        assert uow.connection.execute('SELECT 1 FROM observation_tokens WHERE token_id=?', (old_token,)).fetchone()
        uow.connection.execute("DELETE FROM events WHERE type='observation.completion'")
        env.repos.observations.prune(uow, now=env.clock.now_iso())
        assert uow.connection.execute('SELECT 1 FROM observation_tokens WHERE token_id=?', (old_token,)).fetchone() is None


def test_expired_unrevoked_completion_publisher_is_retained_for_historical_provenance(external):
    env = external
    publish(env, state='idle', current_completion_ref='one', valid_for_seconds=3600)
    old_token = env.credential['token_id']
    advance(env, 901)
    new_token(env)
    publish(env, sequence=2, state='working')
    with env.factory.unit_of_work() as uow:
        env.repos.observations.prune(uow, now=env.clock.now_iso())
        assert uow.connection.execute('SELECT 1 FROM observation_tokens WHERE token_id=?', (old_token,)).fetchone()
    assert view(env, kind='external_completion_unseen')['items'][0]['freshness'] == 'current'


def test_generation_rotation_keeps_old_completion_explicitly_unavailable(external):
    env = external
    publish(env, state='blocked', current_completion_ref='old-generation-end')
    old_generation = env.instance['generation']
    env.instance = env.service.rotate_instance(context=OPERATOR, source_id=env.source['source_id'],
        observed_instance_id=env.instance['observed_instance_id'], body=dict(
            expected_revision=env.source['revision'], expected_generation=old_generation))['instance']
    new_token(env)
    publish(env, state='working')
    assert view(env, kind='external_blocked')['total'] == 0
    assert view(env, kind='external_completion_unseen')['total'] == 0
    history = view(env, kind='external_completion_unseen', state='all')['items'][0]
    assert history['external_observation']['generation'] == old_generation
    assert history['freshness'] == 'unavailable'


@pytest.mark.parametrize('change', [
    "UPDATE agents SET is_active=0 WHERE agent_id='alice'",
    "UPDATE agents SET permissions='{}' WHERE agent_id='alice'",
    "UPDATE agents SET api_key_hash='changed-key' WHERE agent_id='alice'",
    "DELETE FROM observation_source_workspaces",
])
def test_current_authority_loss_hides_external_actions_without_erasing_history(external, change):
    env = external
    publish(env, state='blocked', current_completion_ref='one')
    with env.factory.unit_of_work() as uow:
        uow.connection.execute(change)
    assert view(env)['total'] == 0
    values = view(env, state='all')['items']
    assert len(values) == 2
    assert all(not item['active'] and item['freshness'] == 'unavailable' for item in values)


def test_observation_feature_off_keeps_history_but_no_active_external_occurrences(external):
    env = external
    publish(env, state='blocked', current_completion_ref='one')
    env.config.feature_observations = False
    before = snapshot(env, auxiliary=True)
    assert view(env)['total'] == 0
    assert all(item['external_observation']['activity_state'] == 'unknown'
               for item in view(env, state='all')['items'])
    assert snapshot(env, auxiliary=True) == before
    env.config.feature_observations = True
    assert view(env)['total'] == 2
    env.config.feature_attention = False
    with pytest.raises(OktoNexusError, match='FEATURE_DISABLED'):
        view(env)
    assert env.service.get_instance(context=OPERATOR, observed_instance_id=env.instance['observed_instance_id'])['item']['activity_state'] == 'blocked'


def test_completion_retention_removes_only_retained_event_occurrence(external):
    env = external
    publish(env, state='idle', current_completion_ref='one')
    publish(env, sequence=2, state='idle', current_completion_ref='two')
    with env.factory.unit_of_work() as uow:
        env.repos.observations.prune_events(uow, cutoff='2000-01-01T00:00:00Z', max_events=1)
    values = view(env, kind='external_completion_unseen')['items']
    assert len(values) == 1
    assert values[0]['external_observation']['last_report']['current_completion_ref'] == 'two'
    replay = publish(env, sequence=2, state='idle', current_completion_ref='two')
    assert replay['replayed'] is True


def test_legacy_completion_without_remaining_provenance_is_historical_unavailable(external):
    env = external
    publish(env, state='idle', current_completion_ref='one')
    with env.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE events SET payload=json_remove(payload,'$.source_revision','$.publisher_token_id','$.observed_at') WHERE type='observation.completion'")
    assert view(env, kind='external_completion_unseen')['total'] == 1  # Exact head proves the old fields.
    publish(env, sequence=2, state='working')
    assert view(env, kind='external_completion_unseen')['total'] == 0
    legacy = view(env, kind='external_completion_unseen', state='all')['items'][0]
    assert legacy['external_observation']['last_report']['observed_at'] is None
    assert legacy['freshness'] == 'unavailable'


def test_event_failure_rolls_back_head_anchor_and_budget(external, monkeypatch):
    env = external
    before = snapshot(env, auxiliary=True)
    def fail(*args, **kwargs):
        raise OSError('synthetic precommit event failure')
    monkeypatch.setattr(env.service.events, 'emit', fail)
    with pytest.raises(OSError):
        publish(env, state='blocked')
    assert snapshot(env, auxiliary=True) == before


@pytest.mark.parametrize('keep_agents', [True, False])
def test_explicit_reset_clears_anchors_and_history_without_reusing_generation(external, keep_agents):
    env = external
    publish(env, state='blocked', current_completion_ref='one')
    with env.factory.unit_of_work() as uow:
        high = uow.connection.execute('SELECT last_generation FROM observation_installation').fetchone()[0]
        clear_operational_history(uow.connection, keep_agents=keep_agents)
        assert uow.connection.execute('SELECT count(*) FROM observation_attention_anchors').fetchone()[0] == 0
        assert uow.connection.execute('SELECT last_generation FROM observation_installation').fetchone()[0] == high


def test_two_sources_same_alias_remain_independent_and_exact_filtered(external):
    env = external
    publish(env, state='blocked')
    second = deepcopy(dict(source=env.source, instance=env.instance))
    env.source = env.service.create_source(context=OPERATOR, body=dict(agent_id='alice',
        source_kind='hook', workspace_ids=['ws'], registration_ref='other-source'))['source']
    env.instance = env.service.create_instance(context=OPERATOR, source_id=env.source['source_id'], body=dict(
        expected_revision=env.source['revision'], workspace_id='ws', external_instance_ref='occupant-1'))['instance']
    new_token(env)
    publish(env, state='blocked')
    values = view(env, agent_id='alice', workspace_id='ws', kind='external_blocked')['items']
    assert len(values) == 2 and len({item['attention_id'] for item in values}) == 2
    assert {item['source_id'] for item in values} == {second['instance']['observed_instance_id'], env.instance['observed_instance_id']}
    assert all(item['external_observation']['canonical_session_ref'] is None for item in values)
    assert view(env, agent_id='bob')['total'] == 0
    assert view(env, workspace_id='other')['total'] == 0


@pytest.mark.parametrize('field', ['received_at', 'valid_until', 'observed_at'])
@pytest.mark.parametrize('invalid', ['not-a-time', '2099-01-01T00:00:00'])
def test_malformed_or_naive_times_fail_closed_in_every_projection(external, field, invalid):
    env = external
    publish(env, state='blocked')
    with env.factory.unit_of_work() as uow:
        if field == 'observed_at':
            uow.connection.execute("UPDATE observation_heads SET report_json=json_set(report_json,'$.observed_at',?)", (invalid,))
        else:
            uow.connection.execute('UPDATE observation_heads SET ' + field + '=?', (invalid,))
    with pytest.raises((ValueError, TypeError)):
        env.service.read(context=OPERATOR)
    with pytest.raises((ValueError, TypeError)):
        env.service.get_instance(context=OPERATOR, observed_instance_id=env.instance['observed_instance_id'])
    with pytest.raises((ValueError, TypeError)):
        env.service.summary(context=OPERATOR)
    with pytest.raises(OktoNexusError, match='DB_ERROR'):
        view(env, kind='external_blocked')


def test_inconsistent_receipt_deadline_is_not_current(external):
    env = external
    publish(env, state='blocked')
    with env.factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE observation_heads SET valid_until=received_at')
    with pytest.raises(ValueError):
        env.service.summary(context=OPERATOR)
    with pytest.raises(OktoNexusError, match='DB_ERROR'):
        view(env, kind='external_blocked')
