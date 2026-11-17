"""Batch optimization equivalence over authorized SQLite fixture facts, provider zero."""
from contextlib import contextmanager
from dataclasses import asdict

import pytest

from okto_nexus.adapters.outbound.sqlite import home_entries
from okto_nexus.adapters.outbound.sqlite.home_entries import SqliteHomeEntryRelations
from okto_nexus.domain.attention import normalize_filters
from okto_nexus.domain.home import filters as home_filters
from okto_nexus.errors import OktoNexusError
from tests.ui_simplification.test_entry_relations import scenario

__all__ = ['scenario']


@contextmanager
def authorized(s, selection, version):
    service = s.app.state.home
    scope = home_filters(selection)
    with s.factory.unit_of_work(write=False) as uow:
        server, now, config = service._basis(uow, s.operator, scope)
        with service.attention.queries._relation(uow, filters=normalize_filters({'state': 'all'}),
                now=now, config=config, access=service.access, context=s.operator,
                source_scope={'workspace_id': scope.get('workspace_id')}) as relation:
            params = {'server_id': server, 'workspace_id': scope.get('workspace_id'),
                'agent_id': scope.get('agent_id'), 'home_now': now, 'state': 'all',
                'delivery_presentation_version': version}
            yield uow, scope, server, now, relation, params


@pytest.mark.parametrize('version', [1, 2])
@pytest.mark.parametrize('selection', [{}, {'workspace_id': 'ws'}, {'agent_id': 'operator'},
    {'agent_id': 'B'}, {'workspace_id': 'ws', 'agent_id': 'B'}])
def test_batch_rows_equal_isolated_relations_exactly(scenario, version, selection):
    queries = SqliteHomeEntryRelations()
    with authorized(scenario, selection, version) as (uow, _, _, _, relation, params):
        before = uow.connection.total_changes
        batch = queries._work_results(uow, params=params, attention_relation=relation, check_budget=lambda: None)
        old_work = queries._work(uow, params=params, attention_relation=relation)
        old_results = queries._results(uow, params=dict(params, agent_id=None), attention_relation=relation)
        assert batch == (old_work, old_results)  # Includes IDs, previews, references and source revisions.
        assert uow.connection.total_changes == before


@pytest.mark.parametrize('version', [1, 2])
def test_unavailable_workspace_refuses_before_batch(scenario, version, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('An unavailable workspace must fail authorization/basis before batch projection')
    monkeypatch.setattr(SqliteHomeEntryRelations, '_work_results', unexpected)
    with pytest.raises(OktoNexusError) as error, authorized(scenario, {'workspace_id': 'missing-workspace'}, version):
        pytest.fail('Unavailable workspace must not become an empty authorized relation')
    assert error.value.code == 'NOT_FOUND'


def test_authorized_occurrences_materialize_once_for_both_branches(scenario):
    queries = SqliteHomeEntryRelations()
    with authorized(scenario, {}, 2) as (uow, _, _, _, relation, params):
        calls = []
        def observe(value):
            calls.append(1)
            return value
        uow.connection.create_function('batch_count_authorized_occurrence', 1, observe)
        sql, bindings = relation
        counted = ('WITH filtered AS MATERIALIZED (SELECT batch_count_authorized_occurrence(item) AS item FROM ('
            + sql + ' SELECT item FROM filtered))', bindings)
        statements = []
        uow.connection.set_trace_callback(statements.append)
        try:
            batch = queries._work_results(uow, params=params, attention_relation=counted, check_budget=lambda: None)
            once = len(calls)
            assert once > 0
            assert len(statements) == 1
            assert 'home_activity_v1' in statements[0] and 'home_result_v1' in statements[0]
            assert statements[0].count('home_attention_all AS MATERIALIZED') == 1
            calls.clear()
            old = (queries._work(uow, params=params, attention_relation=counted),
                queries._results(uow, params=dict(params, agent_id=None), attention_relation=counted))
            assert batch == old
            assert len(calls) == 2 * once
        finally:
            uow.connection.set_trace_callback(None)
            uow.connection.create_function('batch_count_authorized_occurrence', 1, None)


@pytest.mark.parametrize('version', [1, 2])
def test_full_relation_and_revision_inputs_equal_isolated_path(scenario, version):
    class Isolated(SqliteHomeEntryRelations):
        def _can_batch_work_results(self):
            return False
    with authorized(scenario, {}, version) as (uow, scope, server, now, relation, _):
        kwargs = {'scope': scope, 'server_id': server, 'now': now, 'attention_relation': relation,
            'presentation_version': version}
        batch = SqliteHomeEntryRelations().read(uow, **kwargs)
        old = Isolated().read(uow, **kwargs)
        assert asdict(batch) == asdict(old)  # Complete opaque revision inputs, not only counts.


def test_broken_results_batch_falls_back_without_losing_work(scenario, monkeypatch):
    monkeypatch.setattr(home_entries, 'RESULTS', 'WITH filtered AS (SELECT item FROM nonexistent_batch_source)')
    with authorized(scenario, {}, 1) as (uow, scope, server, now, relation, _):
        value = SqliteHomeEntryRelations().read(uow, scope=scope, server_id=server,
            now=now, attention_relation=relation)
        assert value.source_status['results'] == 'unavailable'
        assert value.source_status['work'] == 'ready'
        assert any(entry.activity for entry in value.entries)
        assert not value.total_is_exact


def test_per_source_ceiling_retains_small_result_source(scenario):
    queries = SqliteHomeEntryRelations()
    queries.MAX_RELATION_ROWS = 1
    with authorized(scenario, {}, 1) as (uow, scope, server, now, relation, _):
        value = queries.read(uow, scope=scope, server_id=server, now=now, attention_relation=relation)
        assert value.source_status['work'] == 'unavailable'
        assert value.source_status['results'] == 'ready'
        assert not value.total_is_exact
        assert not any(entry.activity for entry in value.entries)
        assert sum(len(entry.results) for entry in value.entries) == 1


@pytest.mark.parametrize('error', [RuntimeError('budget exhausted'),
    OktoNexusError('PERMISSION_DENIED', 'controlled authority refusal', {})])
def test_non_sqlite_failure_is_fatal_and_next_query_has_no_live_cursor(scenario, error):
    queries = SqliteHomeEntryRelations()
    with authorized(scenario, {}, 1) as (uow, _, _, _, relation, params):
        def fail():
            raise error
        with pytest.raises(type(error)):
            queries._work_results(uow, params=params, attention_relation=relation, check_budget=fail)
        assert uow.connection.execute('SELECT 1').fetchone()[0] == 1


def test_custom_source_port_keeps_isolation_and_fatal_authority(scenario, monkeypatch):
    queries = SqliteHomeEntryRelations()
    def refuse(*args, **kwargs):
        raise OktoNexusError('PERMISSION_DENIED', 'controlled source port refusal', {})
    monkeypatch.setattr(queries, '_results', refuse)
    assert not queries._can_batch_work_results()
    with authorized(scenario, {}, 1) as (uow, scope, server, now, relation, _), pytest.raises(OktoNexusError):
        queries.read(uow, scope=scope, server_id=server, now=now, attention_relation=relation)
