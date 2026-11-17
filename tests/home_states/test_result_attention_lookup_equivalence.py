"""Request-local lookup equivalence, authorized SQLite reads; no native execution."""
import json
import sqlite3
from copy import deepcopy
from dataclasses import asdict

import pytest

from okto_nexus.adapters.outbound.sqlite import home_entries
from okto_nexus.adapters.outbound.sqlite.home import result_attention
from okto_nexus.adapters.outbound.sqlite.home_entries import SqliteHomeEntryRelations
from okto_nexus.domain.attention import canonical
from okto_nexus.errors import OktoNexusError
from tests.home_states.test_projection_batch import authorized, scenario

__all__ = ['scenario']


class LegacyLookup(SqliteHomeEntryRelations):
    def _result_attention_index(self, *args, **kwargs):
        return None


def _arguments(scope, server, now, relation, version=2):
    return {'scope': scope, 'server_id': server, 'now': now,
        'attention_relation': relation, 'presentation_version': version}


def _relation(values):
    return ('WITH filtered AS MATERIALIZED (SELECT value AS item FROM json_each(:lookup_values))',
        {'lookup_values': canonical(values)})


def _raw_results(queries, uow, params, relation):
    ctes, additions = queries.home._attention_relations(relation)
    raw = home_entries.RESULTS.replace(home_entries._RESULT_ATTENTION_FILTER,
        'filtered AS MATERIALIZED (SELECT item FROM projected)')
    with queries.home.bounded(uow.connection):
        return queries._collect(uow.connection.execute(ctes + ',' + raw.lstrip()[4:]
            + ' SELECT item FROM filtered', dict(params, agent_id=None, **additions)),
            lambda row: json.loads(row[0]))


def _tracking_case(queries, uow, relation, params, *, seen=False):
    occurrences = queries._attention(uow, relation)
    raw = _raw_results(queries, uow, params, relation)
    assert occurrences and raw  # Real fixture relations, not an empty equivalence.
    value = deepcopy(occurrences[0])
    value.update(attention_id=raw[0]['_attention_id'], workspace_id=raw[0]['workspace_id'])
    value['seen_state'] = dict(value['seen_state'], seen=seen)
    return raw[0], value


@pytest.mark.parametrize('version', [1, 2])
@pytest.mark.parametrize('selection', [{}, {'workspace_id': 'ws'}, {'agent_id': 'B'}])
def test_complete_relation_dto_revision_inputs_and_progress_equal_legacy(scenario, version, selection, monkeypatch):
    queries = SqliteHomeEntryRelations()
    decoded_results = []
    project = home_entries.result_attention_value
    def observe_projection(item, value):
        decoded_results.append(item['id'])
        return project(item, value)
    monkeypatch.setattr(home_entries, 'result_attention_value', observe_projection)
    with authorized(scenario, selection, version) as (uow, scope, server, now, relation, _):
        before = uow.connection.total_changes
        statements = []
        uow.connection.set_trace_callback(statements.append)
        try:
            actual = queries.read(uow, **_arguments(scope, server, now, relation, version))
        finally:
            uow.connection.set_trace_callback(None)
        expected = LegacyLookup().read(uow, **_arguments(scope, server, now, relation, version))
        assert asdict(actual) == asdict(expected)
        assert actual.source_status['results'] == 'ready'
        if version == 1 and selection.get('agent_id') == 'B':
            assert not any(entry.results for entry in actual.entries)
        else:
            assert any(entry.results for entry in actual.entries)
        # Attention's own source relation also UNIONs a 'results' family.
        # Match this adapter's explicit outer section, not that source SQL.
        batch = [s for s in statements if " SELECT 'work' AS section,item," in s]
        assert len(batch) == 1
        assert ('home_result_attention_v1(item,' in batch[0]) is (version == 1)
        assert bool(decoded_results) is (version == 2)
        isolated_results = [s for s in statements if 'home_result_v1(fact)' in s
            and s not in batch]
        assert not isolated_results  # A failed fast batch must not masquerade as fastpath coverage.
        assert uow.connection.total_changes == before


@pytest.mark.parametrize('seen', [False, True])
def test_seen_unseen_exact_occurrence_and_independent_decoded_values(scenario, seen):
    queries = SqliteHomeEntryRelations()
    with authorized(scenario, {}, 2) as (uow, _, _, _, authorized_relation, params):
        raw, value = _tracking_case(queries, uow, authorized_relation, params, seen=seen)
        relation = _relation([value])
        occurrences = queries._attention(uow, relation)
        before = deepcopy(occurrences)
        index = queries._result_attention_index(uow, relation, occurrences, params, lambda: None)
        assert index is not None
        actual = queries._work_results(uow, params=params, attention_relation=relation,
            check_budget=lambda: None, result_attention_index=index)
        expected = queries._work_results(uow, params=params, attention_relation=relation,
            check_budget=lambda: None)
        assert actual == expected
        matched = next(item for item in actual[1] if item['id'] == raw['id'])
        assert matched['attention'] == value
        assert matched['view_state'] == ('seen' if seen else 'unseen')
        assert '_attention_id' not in matched
        matched['attention']['seen_state']['seen'] = not seen
        assert occurrences == before  # No new alias to the collected authority facts.
        assert expected[1] != actual[1]


@pytest.mark.parametrize('case', ['duplicate', 'cross_workspace_duplicate', 'malformed', 'nonfinite'])
def test_ambiguous_or_malformed_occurrences_keep_legacy_sql(scenario, case):
    queries = SqliteHomeEntryRelations()
    with authorized(scenario, {}, 2) as (uow, _, _, _, relation, params):
        _, value = _tracking_case(queries, uow, relation, params)
        values = [value]
        if case in ('duplicate', 'cross_workspace_duplicate'):
            other = deepcopy(value)
            other['seen_state']['seen'] = True
            if case == 'cross_workspace_duplicate':
                other['workspace_id'] = 'different-workspace'
            values.append(other)
        elif case == 'malformed':
            value['seen_state'] = None
        else:
            value['unexpected'] = float('nan')
        before = deepcopy(values)
        assert queries._result_attention_index(uow, relation, values, params, lambda: None) is None
        if case != 'nonfinite':
            custom = _relation(values)
            if case == 'malformed':
                with pytest.raises(sqlite3.Error):
                    queries._work_results(uow, params=params, attention_relation=custom,
                        check_budget=lambda: None)
            else:
                # Scalar first-match behavior is preserved, including duplicates.
                actual = queries._work_results(uow, params=params, attention_relation=custom,
                    check_budget=lambda: None)
                assert next(item for item in actual[1]
                    if item['attention'] and item['attention']['attention_id'] == value['attention_id'])['attention'] == value
        else:
            assert values[0]['unexpected'] != values[0]['unexpected']
            before[0].pop('unexpected')
            comparison = deepcopy(values)
            comparison[0].pop('unexpected')
            assert comparison == before


def test_workspace_partition_missing_tracking_and_cross_executor_are_exact(scenario):
    queries = SqliteHomeEntryRelations()
    with authorized(scenario, {'workspace_id': 'ws'}, 2) as (uow, _, _, _, original, params):
        raw, value = _tracking_case(queries, uow, original, params)
        foreign = deepcopy(value)
        foreign['workspace_id'] = 'foreign-workspace'
        relation = _relation([foreign])
        index = queries._result_attention_index(uow, relation, queries._attention(uow, relation), params, lambda: None)
        assert index is not None and not index.occurrences
        actual = queries._work_results(uow, params=params, attention_relation=relation,
            check_budget=lambda: None, result_attention_index=index)
        expected = queries._work_results(uow, params=params, attention_relation=relation, check_budget=lambda: None)
        assert actual == expected
        matched = next(item for item in actual[1] if item['id'] == raw['id'])
        assert matched['attention'] is None and matched['view_state'] == 'not_tracked'
        # Lookup identity is the exact Attention ID, never executor or labels.
        foreign['workspace_id'] = value['workspace_id']
        foreign['executor_id'] = 'another-executor'
        relation = _relation([foreign])
        index = queries._result_attention_index(uow, relation, queries._attention(uow, relation), params, lambda: None)
        assert index is not None
        assert queries._work_results(uow, params=params, attention_relation=relation,
            check_budget=lambda: None, result_attention_index=index) == queries._work_results(
                uow, params=params, attention_relation=relation, check_budget=lambda: None)


def test_index_is_bound_to_uow_relation_scope_and_version(scenario):
    queries = SqliteHomeEntryRelations()
    with authorized(scenario, {}, 2) as (uow, _, _, _, relation, params):
        index = queries._result_attention_index(uow, relation, queries._attention(uow, relation), params, lambda: None)
        assert index is not None
        for key, value in [('connection', object()), ('relation', object()), ('workspace_id', 'other')]:
            previous = getattr(index, key)
            setattr(index, key, value)
            actual = queries._work_results(uow, params=params, attention_relation=relation,
                check_budget=lambda: None, result_attention_index=index)
            setattr(index, key, previous)
            assert actual == queries._work_results(uow, params=params,
                attention_relation=relation, check_budget=lambda: None)
        assert queries._result_attention_index(uow, relation, [], dict(params,
            delivery_presentation_version=1), lambda: None) is None
        assert queries._result_attention_index(uow, None, [], params, lambda: None) is None


def test_custom_collector_and_partial_attention_fall_back_without_fake_zero(scenario, monkeypatch):
    queries = SqliteHomeEntryRelations()
    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError('controlled unavailable Attention')
    monkeypatch.setattr(queries, '_attention', unavailable)
    with authorized(scenario, {}, 2) as (uow, scope, server, now, relation, params):
        assert queries._result_attention_index(uow, relation, [], params, lambda: None) is None
        value = queries.read(uow, **_arguments(scope, server, now, relation))
        assert value.source_status['attention'] == 'unavailable'
        assert value.source_status['results'] == 'ready'
        assert not value.total_is_exact
        assert all(item['attention'] is None for entry in value.entries for item in entry.results)


def test_transform_failure_is_sqlite_error_and_work_survives_isolated_retry(scenario, monkeypatch):
    def failed(*args):
        raise ValueError('controlled decoded projection failure')
    monkeypatch.setattr(home_entries, 'result_attention_value', failed)
    with authorized(scenario, {}, 2) as (uow, scope, server, now, relation, _):
        before = uow.connection.total_changes
        actual = SqliteHomeEntryRelations().read(uow, **_arguments(scope, server, now, relation))
        expected = LegacyLookup().read(uow, **_arguments(scope, server, now, relation))
        assert asdict(actual) == asdict(expected)
        assert actual.source_status['work'] == actual.source_status['results'] == 'ready'
        assert uow.connection.total_changes == before


@pytest.mark.parametrize('error', [RuntimeError('budget'),
    OktoNexusError('PERMISSION_DENIED', 'controlled authority refusal', {})])
def test_budget_and_authority_failures_remain_fatal_with_cursor_cleanup(scenario, error):
    queries = SqliteHomeEntryRelations()
    with authorized(scenario, {}, 2) as (uow, _, _, _, relation, params):
        index = queries._result_attention_index(uow, relation, queries._attention(uow, relation), params, lambda: None)
        assert index is not None
        def fail():
            raise error
        with pytest.raises(type(error)):
            queries._work_results(uow, params=params, attention_relation=relation,
                check_budget=fail, result_attention_index=index)
        assert uow.connection.execute('SELECT 1').fetchone()[0] == 1


def test_decoded_projection_preserves_legacy_json_contract():
    raw = {'id': 'result-test', '_attention_id': 'private', 'workspace_id': 'ws'}
    occurrence = {'attention_id': 'private', 'workspace_id': 'ws', 'seen_state': {'seen': True}}
    index = home_entries._ResultAttentionIndex(None, None, None, {'private': occurrence})
    assert index.project(deepcopy(raw)) == json.loads(result_attention(canonical(raw), canonical(occurrence)))
    assert '_attention_id' in raw
    assert occurrence['seen_state']['seen'] is True


@pytest.mark.parametrize('raw', [None, [], {'_attention_id': []}])
def test_malformed_decoded_result_has_sqlite_udf_error_boundary(raw):
    index = home_entries._ResultAttentionIndex(None, None, None, {})
    with pytest.raises(sqlite3.Error):
        index.project(raw)


def test_index_does_not_reuse_occurrences_between_reads(scenario):
    queries = SqliteHomeEntryRelations()
    with authorized(scenario, {}, 2) as (uow, _, _, _, authorized_relation, params):
        raw, value = _tracking_case(queries, uow, authorized_relation, params)
        observed = []
        for seen in (False, True, False):
            current = deepcopy(value)
            current['seen_state']['seen'] = seen
            relation = _relation([current])
            index = queries._result_attention_index(uow, relation,
                queries._attention(uow, relation), params, lambda: None)
            assert index is not None
            projected = queries._work_results(uow, params=params, attention_relation=relation,
                check_budget=lambda: None, result_attention_index=index)
            observed.append(next(item for item in projected[1] if item['id'] == raw['id']))
        assert [item['view_state'] for item in observed] == ['unseen', 'seen', 'unseen']


def test_broken_results_and_resource_limit_preserve_other_sources(scenario, monkeypatch):
    with authorized(scenario, {}, 2) as (uow, scope, server, now, relation, _):
        arguments = _arguments(scope, server, now, relation)
        before = uow.connection.total_changes
        original = home_entries.RESULTS
        monkeypatch.setattr(home_entries, 'RESULTS', 'WITH filtered AS (SELECT item FROM nonexistent_r7_source)')
        actual = SqliteHomeEntryRelations().read(uow, **arguments)
        assert actual.source_status['results'] == 'unavailable'
        assert actual.source_status['work'] == 'ready'
        assert not actual.total_is_exact
        monkeypatch.setattr(home_entries, 'RESULTS', original)
        limited = SqliteHomeEntryRelations()
        limited.MAX_RELATION_ROWS = 1
        actual = limited.read(uow, **arguments)
        expected = LegacyLookup()
        expected.MAX_RELATION_ROWS = 1
        assert asdict(actual) == asdict(expected.read(uow, **arguments))
        assert not actual.total_is_exact
        assert uow.connection.total_changes == before
