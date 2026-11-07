"""External source pruning preserves metadata and avoids unrelated projection."""
from copy import deepcopy

import pytest

from okto_nexus.adapters.outbound.sqlite import attention_external
from okto_nexus.adapters.outbound.sqlite.attention import SqliteAttentionQueries
from okto_nexus.errors import OktoNexusError
from test_attention_external import external as _external_fixture
from test_observation_service import OPERATOR, advance, obs as _obs_fixture

external, obs = _external_fixture, _obs_fixture


def mixed(env):
    instances = [env.instance]
    with env.factory.unit_of_work() as uow:
        for index in range(1, 8):
            instances.append(env.repos.observations.create_instance(uow,
                source_id=env.source['source_id'], expected_revision=env.source['revision'],
                workspace_id='ws', external_instance_ref='query-case-' + str(index), now=env.clock.now_iso()))
    token = env.service.issue_token(context=OPERATOR, source_id=env.source['source_id'], body=dict(
        expected_revision=env.source['revision'], instance_grants=[dict(
            observed_instance_id=item['observed_instance_id'], generation=item['generation']) for item in instances]))['token']
    reports = []
    for index, state in enumerate(['blocked', 'working', 'idle', 'unknown', 'working', 'blocked', 'idle']):
        item = instances[index]
        value = dict(schema_version=1, source_id=env.source['source_id'],
            observed_instance_id=item['observed_instance_id'], generation=item['generation'],
            sequence=1, state=state, evidence='inferred', observed_at=env.clock.now_iso(),
            valid_for_seconds=1 if index >= 4 else 90)
        if index in (2, 6):
            value['current_completion_ref'] = 'completion-' + str(index)
        reports.append(value)
    env.service.publish(token=token, payload={'reports': reports})
    advance(env, 2)
    return instances


@pytest.mark.parametrize('kind, head_indices, completion_indices', [
    (None, [0, 4, 5, 6], [2, 6]),
    ('external_blocked', [0, 5], []),
    ('external_observation_stale', [4, 5, 6], []),
    ('external_completion_unseen', [], [2, 6]),
])
def test_only_relevant_source_rows_reach_full_projection(external, monkeypatch, kind, head_indices, completion_indices):
    env = external
    instances = mixed(env)
    decoded = []
    original = attention_external.decode_facts
    def capture(value):
        decoded.append((value['current']['observed_instance_id'], value['completion'] is not None))
        return original(value)
    monkeypatch.setattr(attention_external, 'decode_facts', capture)
    filters = dict(state='all', workspace_id='ws', agent_id='alice')
    if kind:
        filters['kind'] = kind
    result = env.attention.summary(context=OPERATOR, filters=filters)
    assert set(decoded) == {(instances[index]['observed_instance_id'], False) for index in head_indices} | {
        (instances[index]['observed_instance_id'], True) for index in completion_indices}
    assert len(decoded) == len(head_indices) + len(completion_indices)
    assert result['total'] == (7 if kind is None else 3 if kind == 'external_observation_stale' else 2)
    assert SqliteAttentionQueries.QUERY_SECONDS == 5.0


@pytest.mark.parametrize('state', ['active', 'all', 'open', 'expired', 'resolved'])
def test_kind_pushdown_preserves_exact_items_preferences_and_totals(external, state):
    env = external
    mixed(env)
    initial = env.attention.read(context=OPERATOR, filters=dict(state='all'), limit=200)
    completion = next(item for item in initial['items'] if item['kind'] == 'external_completion_unseen')
    env.attention.mark_seen(context=OPERATOR, attention_id=completion['attention_id'],
        source_revision=completion['source_revision'], preference_revision=0)
    whole = env.attention.read(context=OPERATOR, filters=dict(state=state), limit=200)
    for kind in ('external_blocked', 'external_observation_stale', 'external_completion_unseen'):
        filtered = env.attention.read(context=OPERATOR, filters=dict(state=state, kind=kind), limit=200)
        expected = [item for item in whole['items'] if item['kind'] == kind]
        assert filtered['items'] == expected
        assert filtered['total'] == len(expected)
        assert filtered['counts']['watch'] == len(expected)
        assert filtered['counts']['unseen'] == sum(not item['seen_state']['seen'] for item in expected)
        assert 0 < filtered['refresh_after_seconds'] <= 15


def test_scope_filters_prune_before_any_external_projection(external, monkeypatch):
    env = external
    mixed(env)
    def unwanted(_):
        pytest.fail('An unrelated external source reached projection.')
    monkeypatch.setattr(attention_external, 'decode_facts', unwanted)
    for filters in (dict(agent_id='bob'), dict(workspace_id='other')):
        assert env.attention.summary(context=OPERATOR, filters=filters)['total'] == 0


def test_unreported_instances_and_working_heads_do_not_require_full_decode(external, monkeypatch):
    env = external
    def unwanted(_):
        pytest.fail('A non-occurrence reached full projection.')
    monkeypatch.setattr(attention_external, 'decode_facts', unwanted)
    assert env.attention.summary(context=OPERATOR)['total'] == 0
    from test_observation_service import publish
    publish(env, state='working')
    assert env.attention.summary(context=OPERATOR)['total'] == 0


@pytest.mark.parametrize('field, value', [
    ('valid_until', '2099-02-30T00:00:00.000000Z'),
    ('valid_until', 'invalid'),
    ('received_at', '2099-01-01T00:00:00'),
    ('observed_at', 'invalid'),
])
def test_temporal_predicate_does_not_silently_omit_invalid_nonblocked_heads(external, field, value):
    env = external
    from test_observation_service import publish
    publish(env, state='working')
    with env.factory.unit_of_work() as uow:
        if field == 'observed_at':
            uow.connection.execute("UPDATE observation_heads SET report_json=json_set(report_json,'$.observed_at',?)", (value,))
        else:
            uow.connection.execute('UPDATE observation_heads SET ' + field + '=?', (value,))
    for filters in ({}, dict(kind='external_observation_stale')):
        with pytest.raises(OktoNexusError, match='DB_ERROR'):
            env.attention.summary(context=OPERATOR, filters=filters)


def test_decoder_and_historical_projection_do_not_mutate_shared_facts(external):
    from okto_nexus.application.attention_external import project
    env = external
    from test_observation_service import publish
    receipt = publish(env, state='idle', current_completion_ref='one')
    with env.factory.unit_of_work(write=False) as uow:
        row = env.repos.observations.get_current(uow, observed_instance_id=env.instance['observed_instance_id'])
    facts = dict(current=row, anchor=None, completion=dict(event_id=1,
        report=dict(receipt, state='idle', evidence='reported', completion_ref='one'),
        source_revision=env.source['revision'], observed_at=env.clock.now_iso(), publisher_revoked=False))
    before = deepcopy(facts)
    assert project(facts, env.clock.now_iso(), dict(config=env.config, correlations={}))
    assert facts == before
