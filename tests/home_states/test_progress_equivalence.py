"""Progress batching vs the frozen correlated query over synthetic SQLite facts.

The only semantic correction in the oracle is committed_contiguous instead of
the unwritten projected_through. These fixtures do not execute a native harness.
"""
import json
import sqlite3
from pathlib import Path

import pytest
from home_evolution.fixtures import WORKSPACES, home_scenario

from okto_nexus.adapters.outbound.sqlite.home import FACTS
from okto_nexus.adapters.outbound.sqlite.home_entries import SqliteHomeEntryRelations

__all__ = ['home_scenario']

LEGACY = (Path(__file__).parent/'fixtures/home_progress_legacy.sql').read_text(encoding='utf-8')
CORRECTED_LEGACY = LEGACY.replace('e.sequence<=w.projected_through', 'e.sequence<=w.committed_contiguous')
SCOPE = {'server_id': 'fixture-server', 'executor_id': 'fixture-executor',
    'session_id': 'fixture-native-session', 'stream_epoch': 'progress-current'}


def copy_row(c, table, row, **changes):
    values = dict(row, **changes)
    c.execute('INSERT INTO '+table+'('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',
        tuple(values.values()))


def prepare(s):
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        c.execute("UPDATE execution_receipts SET stage='ACCEPTED' WHERE operation_id='fixture-success'")
        c.execute("UPDATE execution_operations SET expected_revisions_json=? WHERE operation_id='fixture-success'",
            (json.dumps({'session_owner_generation': 1}),))
        c.execute('UPDATE execution_sessions SET stream_epoch=?', (SCOPE['stream_epoch'],))
        c.execute('INSERT INTO execution_event_watermarks(server_id,executor_id,session_id,stream_epoch,committed_contiguous,projected_through,gap_state) '
            'VALUES(:server_id,:executor_id,:session_id,:stream_epoch,20,0,\'none\')', SCOPE)


def event(c, s, sequence, payload, *, scope=None):
    key = scope or SCOPE
    c.execute('INSERT INTO execution_event_ingress(server_id,executor_id,session_id,stream_epoch,sequence,event_hash,event_type,payload_json,received_at) '
        'VALUES(:server_id,:executor_id,:session_id,:stream_epoch,:sequence,\'synthetic-read-fact\',\'native.event\',:payload,:now)',
        dict(key, sequence=sequence, payload=payload if isinstance(payload, str) else json.dumps(payload), now=s.clock.now_iso()))


def progress(operation='fixture-success', phase='progress'):
    return {'operation_id': operation, 'payload': {'delivery_phase': phase}}


def rows(s, relation, selection=None):
    params = dict(SCOPE, workspace_id=None, agent_id=None, state='all', home_now=s.clock.now_iso(),
        delivery_presentation_version=2)
    params.update(selection or {})
    # Params are caller-authorized read scope in production; fixture facts here
    # compare SQL behavior, not an alternative authorization implementation.
    with s.factory.unit_of_work(write=False) as uow:
        before = uow.connection.total_changes
        value = SqliteHomeEntryRelations()._project(uow, relation=relation, params=params, attention_relation=None)
        assert uow.connection.total_changes == before
        return sorted(value, key=lambda item: item['id'])


@pytest.mark.parametrize('case', ['progress', 'started', 'duplicate', 'unrelated-operation', 'wrong-phase',
    'wrong-epoch', 'uncommitted', 'gap', 'old-owner', 'closed', 'inactive-lease',
    'terminal-receipt', 'newer-terminal-receipt', 'missing-receipt', 'terminal-result',
    'partial-result', 'json-null', 'missing-operation', 'null-operation', 'legacy-payload-string'])
def test_batched_progress_equals_corrected_correlated_oracle(home_scenario, case):
    s = home_scenario
    prepare(s)
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        payload = progress()
        key, sequence = SCOPE, 1
        if case == 'started':
            payload = progress(phase='started')
        elif case == 'unrelated-operation':
            payload = progress('different-operation')
        elif case == 'wrong-phase':
            payload = progress(phase='completed')
        elif case == 'wrong-epoch':
            key = dict(SCOPE, stream_epoch='older-epoch')
            c.execute('INSERT INTO execution_event_watermarks(server_id,executor_id,session_id,stream_epoch,committed_contiguous,gap_state) '
                'VALUES(:server_id,:executor_id,:session_id,:stream_epoch,20,\'none\')', key)
        elif case == 'uncommitted':
            sequence = 21
        elif case == 'gap':
            c.execute("UPDATE execution_event_watermarks SET gap_state='missing'")
        elif case == 'old-owner':
            c.execute("UPDATE execution_operations SET expected_revisions_json='{\"session_owner_generation\":2}' WHERE operation_id='fixture-success'")
        elif case == 'closed':
            c.execute("UPDATE execution_sessions SET lifecycle_state='CLOSED'")
        elif case == 'inactive-lease':
            c.execute("UPDATE execution_sessions SET lease_state='CLOSED'")
        elif case == 'terminal-receipt':
            c.execute("UPDATE execution_receipts SET stage='SUCCEEDED'")
        elif case == 'newer-terminal-receipt':
            receipt = c.execute("SELECT * FROM execution_receipts WHERE operation_id='fixture-success'").fetchone()
            copy_row(c, 'execution_receipts', receipt, receipt_revision=2, stage='CANCELLED')
        elif case == 'missing-receipt':
            c.execute("DELETE FROM execution_receipts WHERE operation_id='fixture-success'")
        elif case in {'terminal-result', 'partial-result'}:
            # The terminal capture FK references admitted ingress, so seed the
            # synthetic referenced row before inserting its result metadata.
            event(c, s, sequence, payload, scope=key)
            c.execute('INSERT INTO execution_results(server_id,executor_id,operation_id,session_id,stream_epoch,terminal_sequence,captured_at) '
                'VALUES(:server_id,:executor_id,\'fixture-success\',:session_id,:stream_epoch,:terminal,:now)',
                dict(SCOPE, terminal=1 if case == 'terminal-result' else None, now=s.clock.now_iso()))
        elif case == 'json-null':
            payload = 'null'
        elif case == 'missing-operation':
            payload = {'payload': {'delivery_phase': 'progress'}}
        elif case == 'null-operation':
            payload = progress(None)
        elif case == 'legacy-payload-string':
            payload = {'operation_id': 'fixture-success', 'payload': json.dumps({'delivery_phase': 'progress'})}
        if case not in {'terminal-result', 'partial-result'}:
            event(c, s, sequence, payload, scope=key)
        if case == 'duplicate':
            event(c, s, 2, progress(phase='started'))
    expected = rows(s, CORRECTED_LEGACY)
    assert rows(s, FACTS) == expected
    own = next(item for item in expected if item['source_ref']['id'] == 'fixture-success')
    assert own['running_count'] == (1 if case in {'progress', 'started', 'duplicate', 'partial-result'} else 0)
    for selection in ({'workspace_id': WORKSPACES[0]}, {'workspace_id': WORKSPACES[1]},
            {'agent_id': 'A'}, {'agent_id': 'B'}, {'server_id': 'different-server'}):
        assert rows(s, FACTS, selection) == rows(s, CORRECTED_LEGACY, selection)


def test_committed_progress_corrects_dead_projection_field_without_changing_identity(home_scenario):
    s = home_scenario
    prepare(s)
    with s.factory.unit_of_work() as uow:
        event(uow.connection, s, 1, progress())
    old = next(item for item in rows(s, LEGACY) if item['source_ref']['id'] == 'fixture-success')
    new = next(item for item in rows(s, FACTS) if item['source_ref']['id'] == 'fixture-success')
    assert old['display_state'] == 'native_accepted' and old['running_count'] == 0
    assert new['display_state'] == 'running' and new['running_count'] == 1
    assert old['id'] == new['id'] and old['detail_target'] == new['detail_target']
    assert old.keys() == new.keys()
    assert old['source_ref']['revision'] != new['source_ref']['revision']  # Factual status correction, including v1.


@pytest.mark.parametrize('order', ['valid-before-malformed', 'malformed-before-valid'])
def test_malformed_session_retains_exact_legacy_exists_shortcircuit(home_scenario, order):
    s = home_scenario
    prepare(s)
    with s.factory.unit_of_work() as uow:
        event(uow.connection, s, 1, progress() if order == 'valid-before-malformed' else '{invalid')
        event(uow.connection, s, 2, '{invalid' if order == 'valid-before-malformed' else progress())
    if order == 'valid-before-malformed':
        assert rows(s, FACTS) == rows(s, CORRECTED_LEGACY)
        assert next(item for item in rows(s, FACTS) if item['source_ref']['id'] == 'fixture-success')['running_count'] == 1
    else:
        for relation in (CORRECTED_LEGACY, FACTS):
            with pytest.raises(sqlite3.OperationalError, match='malformed JSON'):
                rows(s, relation)


@pytest.mark.parametrize('case', ['uncommitted', 'old-epoch', 'ineligible-session', 'gap'])
def test_out_of_scope_malformed_history_does_not_poison_projection(home_scenario, case):
    s = home_scenario
    prepare(s)
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        key = dict(SCOPE, stream_epoch='old-malformed') if case == 'old-epoch' else SCOPE
        if case == 'old-epoch':
            c.execute('INSERT INTO execution_event_watermarks(server_id,executor_id,session_id,stream_epoch,committed_contiguous,gap_state) '
                'VALUES(:server_id,:executor_id,:session_id,:stream_epoch,20,\'none\')', key)
        if case == 'ineligible-session':
            c.execute("UPDATE execution_sessions SET lifecycle_state='CLOSED'")
        elif case == 'gap':
            c.execute("UPDATE execution_event_watermarks SET gap_state='missing'")
        event(c, s, 21 if case == 'uncommitted' else 1, '{invalid', scope=key)
    assert rows(s, FACTS) == rows(s, CORRECTED_LEGACY)


def test_progress_relation_is_batched_once_in_query_plan(home_scenario):
    s = home_scenario
    prepare(s)
    with s.factory.unit_of_work() as uow:
        event(uow.connection, s, 1, progress())
    queries = SqliteHomeEntryRelations()
    with s.factory.unit_of_work(write=False) as uow, queries.home.bounded(uow.connection):
        sql = 'WITH home_attention AS MATERIALIZED (SELECT NULL AS item WHERE 0),' + FACTS.lstrip()[4:] + ' SELECT item FROM filtered'
        params = dict(SCOPE, workspace_id=None, agent_id=None, state='all', home_now=s.clock.now_iso())
        plan = [row[3] for row in uow.connection.execute('EXPLAIN QUERY PLAN '+sql, params)]
        assert plan.count('MATERIALIZE progress_keys') == 1
        assert 'MATERIALIZE progress_sessions' in plan
        assert any(line.startswith(('SCAN progress ', 'SEARCH progress ')) for line in plan)
        assert any(line.startswith(('SCAN invalid_progress ', 'SEARCH invalid_progress ')) for line in plan)

    # EXPLAIN may legitimately choose SCAN for this tiny materialized relation.
    # A read-only probe additionally proves valid history never enters the
    # retained correlated fallback; malformed history alone activates it.
    needle = "json_extract(e.payload_json,'$.operation_id')=o.operation_id"
    assert FACTS.count(needle) == 1
    instrumented = FACTS.replace(needle, 'progress_test_fallback_probe(e.payload_json)=o.operation_id')
    calls = []
    def probe(raw):
        calls.append(1)
        return json.loads(raw).get('operation_id')
    def run_probe():
        with s.factory.unit_of_work(write=False) as uow, queries.home.bounded(uow.connection):
            before = uow.connection.total_changes
            uow.connection.create_function('progress_test_fallback_probe', 1, probe)
            try:
                sql = 'WITH home_attention AS MATERIALIZED (SELECT NULL AS item WHERE 0),' + instrumented.lstrip()[4:] + ' SELECT item FROM filtered'
                uow.connection.execute(sql, params).fetchall()
                assert uow.connection.total_changes == before
            finally:
                uow.connection.create_function('progress_test_fallback_probe', 1, None)
    run_probe()
    assert calls == []
    with s.factory.unit_of_work() as uow:
        event(uow.connection, s, 2, '{invalid')
    run_probe()
    assert calls


def test_duplicate_json_scalar_types_do_not_duplicate_a_text_operation(home_scenario):
    s = home_scenario
    prepare(s)
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        original = c.execute("SELECT * FROM execution_operations WHERE operation_id='fixture-success'").fetchone()
        receipt = c.execute("SELECT * FROM execution_receipts WHERE operation_id='fixture-success'").fetchone()
        copy_row(c, 'execution_operations', original, operation_id='123')
        copy_row(c, 'execution_receipts', receipt, operation_id='123')
        event(c, s, 1, progress(123))
        event(c, s, 2, progress('123'))
    actual = rows(s, FACTS)
    assert actual == rows(s, CORRECTED_LEGACY)
    operation = next(item for item in actual if item['source_ref']['id'] == '123')
    assert operation['running_count'] == operation['attempt_count'] == 1
    assert len({item['id'] for item in actual}) == len(actual)


@pytest.mark.parametrize('different', ['session', 'executor', 'server', 'workspace'])
def test_progress_keys_cannot_leak_from_another_full_scope(home_scenario, different):
    """Synthetic migrated read facts, not a manufactured authority/launch proof."""
    s = home_scenario
    prepare(s)
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        key = dict(SCOPE, session_id='side-session')
        if different == 'executor':
            key['executor_id'] = 'side-executor'
        elif different == 'server':
            key['server_id'] = 'side-server'
        workspace = WORKSPACES[1] if different == 'workspace' else WORKSPACES[0]
        executor = c.execute('SELECT * FROM execution_executors').fetchone()
        if different in {'executor', 'server'}:
            copy_row(c, 'execution_executors', executor, server_id=key['server_id'],
                executor_id=key['executor_id'], kind='remote', connector_id='progress-read-fixture-connector',
                registered_by_agent_id='A')  # Own synthetic metadata; no Connector login, key or grant.
        endpoint = c.execute("SELECT * FROM agent_endpoints WHERE endpoint_id='fixture-endpoint'").fetchone()
        copy_row(c, 'agent_endpoints', endpoint, endpoint_id='side-endpoint', workspace_id=workspace)
        binding = c.execute("SELECT * FROM execution_workspace_bindings WHERE workspace_binding_id='fixture-wb'").fetchone()
        copy_row(c, 'execution_workspace_bindings', binding, server_id=key['server_id'],
            executor_id=key['executor_id'], workspace_binding_id='side-wb', workspace_id=workspace)
        binding = c.execute("SELECT * FROM execution_bindings WHERE binding_id='fixture-binding'").fetchone()
        copy_row(c, 'execution_bindings', binding, server_id=key['server_id'], executor_id=key['executor_id'],
            binding_id='side-binding', endpoint_id='side-endpoint', workspace_binding_id='side-wb')
        opening = c.execute("SELECT * FROM execution_operations WHERE operation_id='fixture-open'").fetchone()
        copy_row(c, 'execution_operations', opening, server_id=key['server_id'], executor_id=key['executor_id'],
            operation_id='side-open', session_id=key['session_id'], binding_id='side-binding',
            workspace_binding_id='side-wb', workspace_id=workspace)
        session = c.execute("SELECT * FROM execution_sessions WHERE session_id='fixture-native-session'").fetchone()
        copy_row(c, 'execution_sessions', session, server_id=key['server_id'], executor_id=key['executor_id'],
            session_id=key['session_id'], open_operation_id='side-open', binding_id='side-binding',
            workspace_binding_id='side-wb', workspace_id=workspace)
        operation = c.execute("SELECT * FROM execution_operations WHERE operation_id='fixture-success'").fetchone()
        receipt = c.execute("SELECT * FROM execution_receipts WHERE operation_id='fixture-success'").fetchone()
        side_id = 'fixture-success' if different in {'executor', 'server'} else 'side-operation'
        copy_row(c, 'execution_operations', operation, server_id=key['server_id'], executor_id=key['executor_id'],
            operation_id=side_id, session_id=key['session_id'], binding_id='side-binding',
            workspace_binding_id='side-wb', workspace_id=workspace)
        copy_row(c, 'execution_receipts', receipt, server_id=key['server_id'], executor_id=key['executor_id'], operation_id=side_id)
        c.execute('INSERT INTO execution_event_watermarks(server_id,executor_id,session_id,stream_epoch,committed_contiguous,gap_state) '
            'VALUES(:server_id,:executor_id,:session_id,:stream_epoch,20,\'none\')', key)
        event(c, s, 1, progress(), scope=key)
    for selection in ({}, {'workspace_id': WORKSPACES[0]}, {'workspace_id': WORKSPACES[1]}):
        actual = rows(s, FACTS, selection)
        assert actual == rows(s, CORRECTED_LEGACY, selection)
        own = [item for item in actual if item['source_ref']['id'] == 'fixture-success'
            and item['detail_target'].get('executor_id') == SCOPE['executor_id']
            and item['detail_target'].get('session_id') == SCOPE['session_id']]
        assert all(item['running_count'] == 0 for item in own)
