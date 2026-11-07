"""Behavioral qualification of occurrence-scoped native correlation preloads."""
import sqlite3

import pytest

from okto_nexus.adapters.outbound.sqlite import attention, attention_external
from okto_nexus.adapters.outbound.sqlite import observation_correlation_projection as batch
from okto_nexus.adapters.outbound.sqlite.observation_correlations_repo import SqliteObservationCorrelationRepo
from okto_nexus.domain.attention import normalize_filters
from okto_nexus.errors import OktoNexusError
from test_attention_external import external as external_fixture
from test_attention_external_query import mixed
from test_observation_service import OPERATOR, obs as obs_fixture
from test_observation_correlations_storage import selection, proof
from test_observation_correlation_reads import (
    reads as reads_fixture, correlation_http as correlation_fixture,
    select, native_receipt, publish, get, ATTENTION,
)

external, obs = external_fixture, obs_fixture
reads, correlation_http = reads_fixture, correlation_fixture


@pytest.fixture
def correlated(request):
    env = request.getfixturevalue('external')
    env.instances = mixed(env)
    repository = SqliteObservationCorrelationRepo()
    with env.factory.unit_of_work() as uow:
        for item in env.instances:
            repository.replace_selection(uow, agent_id='alice', workspace_id='ws', max_records=4096,
                selection=selection(source_id=env.source['source_id'], source_revision=env.source['revision'],
                    observed_instance_id=item['observed_instance_id'], generation=item['generation']),
                proof=proof(), verified_at=env.clock.now_iso(), now=env.clock.now_iso())
    return env


def ids(env, indices):
    return {env.instances[index]['observed_instance_id'] for index in indices}


@pytest.mark.parametrize('filters,expected', [
    ({}, [0,4,5,6]),
    ({'kind':'external_blocked'}, [0,5]),
    ({'kind':'external_observation_stale'}, [4,5,6]),
    ({'kind':'external_completion_unseen'}, []),
    ({'kind':'external_blocked', 'state':'active', 'seen':'unseen'}, [0,5]),
    ({'kind':'external_blocked', 'category':'watch'}, [0,5]),
    ({'workspace_id':'other'}, []),
    ({'agent_id':'bob'}, []),
])
def test_only_matching_blocked_and_stale_heads_reach_native_batch(correlated, monkeypatch, filters, expected):
    env = correlated
    calls = []
    original = batch.load
    def capture(uow, **kwargs):
        assert callable(kwargs['check_budget'])
        calls.append(kwargs['observed_instance_ids'])
        return original(uow, **kwargs)
    monkeypatch.setattr(batch, 'load', capture)
    env.attention.read(context=OPERATOR, filters=dict({'state':'all'}, **filters))
    if filters.get('kind') == 'external_completion_unseen':
        assert calls == []
    else:
        assert len(calls) == 1 and set(calls[0]) == ids(env, expected)
        assert len(calls[0]) == len(set(calls[0]))  # blocked+stale is one native load.


def test_blocked_without_an_anchor_does_not_preload_a_correlation(correlated, monkeypatch):
    env = correlated
    with env.factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE observation_attention_anchors SET blocked_sequence=NULL,blocked_started_at=NULL '
            'WHERE observed_instance_id=?', (env.instances[0]['observed_instance_id'],))
    calls = []
    original = batch.load
    def capture(uow, **kwargs):
        calls.extend(kwargs['observed_instance_ids'])
        return original(uow, **kwargs)
    monkeypatch.setattr(batch, 'load', capture)
    result = env.attention.read(context=OPERATOR, filters={'kind':'external_blocked', 'state':'all'})
    assert set(calls) == ids(env, [5])
    assert result['total'] == 1


@pytest.mark.parametrize('state', ['active','all','expired','resolved'])
def test_pruned_preload_preserves_items_counts_preferences_and_cas_against_full_input(correlated, monkeypatch, state):
    env = correlated
    before = env.attention.read(context=OPERATOR, filters={'state':'all'})
    blocked = next(item for item in before['items'] if item['kind']=='external_blocked' and item['active'])
    env.attention.mark_seen(context=OPERATOR, attention_id=blocked['attention_id'],
        source_revision=blocked['source_revision'], preference_revision=0)
    filters = {'state':state}
    optimized = env.attention.read(context=OPERATOR, filters=filters)
    def superset(uow, *, config, check_budget, **kwargs):
        return dict(config=config, correlations=batch.load(uow, observed_instance_ids=[
            item['observed_instance_id'] for item in env.instances], check_budget=check_budget))
    monkeypatch.setattr(attention_external, 'build_policy', superset)
    reference = env.attention.read(context=OPERATOR, filters=filters)
    assert optimized == reference


def test_native_metadata_and_current_cas_are_unchanged_by_preload_pruning(reads, monkeypatch):
    env = reads
    select(env)
    native_receipt(env)
    publish(env)
    optimized = get(env, ATTENTION+'?kind=external_blocked')
    def superset(uow, *, config, check_budget, **kwargs):
        return dict(config=config, correlations=batch.load(uow,
            observed_instance_ids=[env.instance['observed_instance_id']], check_budget=check_budget))
    monkeypatch.setattr(attention_external, 'build_policy', superset)
    reference = get(env, ATTENTION+'?kind=external_blocked')
    assert optimized['items'] == reference['items']
    assert optimized['counts'] == reference['counts'] and optimized['snapshot_revision'] == reference['snapshot_revision']
    assert optimized['items'][0]['external_observation']['canonical_observation']['last_received_receipt']['stage'] == 'SUCCEEDED'


def assert_callbacks_removed(conn):
    with pytest.raises(sqlite3.Error):
        conn.execute("SELECT nexus_external_expired_v1('2026-01-02T00:00:00Z','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',NULL,'2026-01-01T00:00:00Z')").fetchone()


def test_policy_error_removes_early_registered_callbacks_and_expired_handler(correlated, monkeypatch):
    env = correlated
    clock = [0.0]
    monkeypatch.setattr(attention.time, 'monotonic', lambda: clock[0])
    def fail(uow, **kwargs):
        assert uow.connection.execute("SELECT nexus_external_expired_v1('2026-01-02T00:00:00Z','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',NULL,'2026-01-01T00:00:00Z')").fetchone()[0] == 0
        clock[0] = 6.0
        raise RuntimeError('synthetic-policy-failure')
    monkeypatch.setattr(attention_external, 'build_policy', fail)
    with env.factory.unit_of_work(write=False) as uow:
        with pytest.raises(RuntimeError, match='synthetic-policy-failure'):
            env.attention.queries.snapshot(uow, filters=normalize_filters({'kind':'external_blocked'}),
                now=env.clock.now_iso(), config=env.config, access=env.service.access, context=OPERATOR)
        assert_callbacks_removed(uow.connection)
        assert uow.connection.execute('WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<2000) SELECT sum(x) FROM n').fetchone()[0] == 2001000


@pytest.mark.parametrize('has_correlation', [True, False])
def test_corrupt_temporal_head_is_not_hidden_by_preload_selection(correlated, has_correlation):
    env = correlated
    bad = env.instances[1]['observed_instance_id']  # working, normally not relevant.
    with env.factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE observation_heads SET valid_until=? WHERE observed_instance_id=?', ('not-a-time',bad))
        if not has_correlation:
            uow.connection.execute('DELETE FROM observation_correlations WHERE observed_instance_id=?', (bad,))
    with env.factory.unit_of_work(write=False) as uow:
        with pytest.raises(OktoNexusError) as error:
            env.attention.queries.snapshot(uow, filters=normalize_filters({'kind':'external_observation_stale'}),
                now=env.clock.now_iso(), config=env.config, access=env.service.access, context=OPERATOR)
        assert error.value.code == 'DB_ERROR'
        assert_callbacks_removed(uow.connection)
        assert uow.connection.execute('SELECT 1').fetchone()[0] == 1


def test_feature_disabled_and_completion_history_do_not_load_current_native_facts(correlated, monkeypatch):
    env = correlated
    monkeypatch.setattr(batch, 'load', lambda *a, **k: pytest.fail('unexpected native preload'))
    result = env.attention.read(context=OPERATOR, filters={'kind':'external_completion_unseen', 'state':'all'})
    assert result['total'] == 2
    assert all(item['external_observation']['canonical_session_ref'] is None for item in result['items'])
    env.config.feature_observations = False
    assert env.attention.read(context=OPERATOR, filters={'state':'all'})['items']


def test_native_input_cap_still_refuses_instead_of_returning_a_truncated_projection(correlated, monkeypatch):
    monkeypatch.setattr(batch, 'MAX_RECORDS', 1)
    with pytest.raises(OktoNexusError) as error:
        correlated.attention.read(context=OPERATOR, filters={'kind':'external_blocked', 'state':'all'})
    assert error.value.code == 'VALIDATION_ERROR'
    assert error.value.details['reason'] == 'OBSERVATION_CORRELATION_INVALID_BATCH'


def test_unreported_correlations_do_not_change_queries_items_or_native_input(correlated, monkeypatch):
    env = correlated
    calls, query_counts, results = [], [], []
    original = batch.load
    def capture(uow, **kwargs):
        calls.append(set(kwargs['observed_instance_ids']))
        return original(uow, **kwargs)
    monkeypatch.setattr(batch, 'load', capture)
    for grow in (False, True):
        if grow:
            with env.factory.unit_of_work() as uow:
                for index in range(20):
                    item = env.repos.observations.create_instance(uow, source_id=env.source['source_id'],
                        expected_revision=env.source['revision'], workspace_id='ws', external_instance_ref='unreported-'+str(index), now=env.clock.now_iso())
                    SqliteObservationCorrelationRepo().replace_selection(uow, agent_id='alice', workspace_id='ws', max_records=4096,
                        selection=selection(source_id=env.source['source_id'], source_revision=env.source['revision'],
                            observed_instance_id=item['observed_instance_id'], generation=item['generation']), proof=proof(),
                        verified_at=env.clock.now_iso(), now=env.clock.now_iso())
        with env.factory.unit_of_work(write=False) as uow:
            statements = []
            uow.connection.set_trace_callback(statements.append)
            results.append(env.attention.queries.snapshot(uow, filters=normalize_filters({'kind':'external_blocked','state':'all'}),
                now=env.clock.now_iso(), config=env.config, access=env.service.access, context=OPERATOR))
            uow.connection.set_trace_callback(None)
            assert_callbacks_removed(uow.connection)
        query_counts.append(sum(sql.lstrip().upper().startswith(('SELECT','WITH')) for sql in statements))
    assert calls == [ids(env,[0,5]), ids(env,[0,5])]
    assert results[0] == results[1] and query_counts[0] == query_counts[1] == 4
    assert attention.SqliteAttentionQueries.QUERY_SECONDS == 5.0
