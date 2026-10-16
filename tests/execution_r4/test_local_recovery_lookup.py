"""A single release must not scale with unrelated closed-session history."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from nexus_connector_core import CoreError
from okto_nexus.bootstrap.embedded_reconciliation import EmbeddedReconciliation
from test_embedded_inventory import app_for


def history(tmp_path, count):
    # Use the fully migrated product schema, without starting runtime workers.
    # These are synthetic historical rows: no harness execution is represented.
    deps, _ = app_for(tmp_path / 'home')
    factory = deps.connection_factory
    db = factory.get_connection()
    try:
        db.execute('PRAGMA foreign_keys=OFF')
        db.execute('BEGIN IMMEDIATE')
        operations = ('server_id,executor_id,operation_id,subject_agent_id,actor_agent_id,binding_id,'
            'workspace_id,workspace_binding_id,session_id,action,intent_hash,semantic_payload,'
            'expected_revisions_json,admission_state,created_at')
        sessions = ('server_id,executor_id,session_id,binding_id,workspace_id,workspace_binding_id,'
            'open_operation_id,owner_generation,lifecycle_state,lease_state')
        db.executemany(f'INSERT INTO execution_operations({operations}) VALUES({",".join("?"*15)})',
            (('server','executor',f'open-{i}','agent','agent','binding','workspace','wb',f'session-{i}',
                'runtime.start','hash','{}','{}','RESOLVED_TERMINAL','2026-10-16T00:00:00Z') for i in range(count)))
        db.executemany(f'INSERT INTO execution_sessions({sessions}) VALUES({",".join("?"*10)})',
            (('server','executor',f'session-{i}','binding','workspace','wb',f'open-{i}',1,'CLOSED','CLOSED')
                for i in range(count)))
        db.execute('COMMIT')
    finally:
        db.close()
    stats = dict(steps=0, verifications=0)
    def progress():
        stats['steps'] += 1
        return 0
    @contextmanager
    def unit_of_work(*, write=False):
        assert not write
        with factory.unit_of_work(write=False) as uow:
            uow.connection.set_progress_handler(progress, 1)
            try:
                yield uow
            finally:
                uow.connection.set_progress_handler(None, 0)
    def verify(*, uow):
        stats['verifications'] += 1
    owner = SimpleNamespace(factory=SimpleNamespace(unit_of_work=unit_of_work), verify=verify,
        channel=SimpleNamespace(server_id='server', executor_id='executor'))
    return EmbeddedReconciliation(owner), factory, stats


@pytest.mark.parametrize('count', [1_000, 10_000, 100_000])
def test_exact_release_lookup_has_bounded_sql_work_with_growing_history(tmp_path, count, record_property):
    reconciliation, _, stats = history(tmp_path, count)
    target = f'session-{count-1}'
    rows = reconciliation._records(session_id=target)
    assert len(rows) == 1 and rows[0]['session_id'] == target
    assert rows[0]['open_operation_id'] == f'open-{count-1}'
    assert stats['verifications'] == 1
    # Count SQLite VM instructions, not a machine-load-sensitive duration.
    record_property('history_sessions', count)
    record_property('lookup_vm_steps', stats['steps'])
    assert stats['steps'] < 500, stats
    before = stats['steps']
    assert reconciliation._records(session_id='missing') == []
    record_property('missing_lookup_vm_steps', stats['steps'] - before)
    assert stats['steps'] - before < 500
    assert reconciliation._records('other-agent', session_id=target) == []
    reconciliation.owner.channel.executor_id = 'other-executor'
    assert reconciliation._records(session_id=target) == []


def test_exact_lookup_preserves_ambiguous_streams_instead_of_choosing_one(tmp_path):
    reconciliation, factory, _ = history(tmp_path, 1)
    with factory.unit_of_work() as uow:
        for stream in ('first', 'second'):
            uow.connection.execute('INSERT INTO execution_local_streams '
                '(server_id,executor_id,session_id,stream_epoch,opening_operation_id,binding_id,agent_id) '
                "VALUES('server','executor','session-0',?,'open-0','binding','agent')", (stream,))
    rows = reconciliation._records(session_id='session-0')
    assert len(rows) == 2 and {r['stream_epoch'] for r in rows} == {'first', 'second'}


@pytest.mark.asyncio
@pytest.mark.parametrize('rows', [[], [{'session_id':'target'}, {'session_id':'target'}]])
async def test_release_requests_exact_identity_and_rejects_missing_or_ambiguous_records(rows):
    owner = SimpleNamespace(host=object())
    reconciliation = EmbeddedReconciliation(owner)
    calls = []
    def records(agent_id=None, *, session_id=None):
        calls.append((agent_id, session_id))
        return rows
    reconciliation._records = records
    with pytest.raises(CoreError) as failure:
        await reconciliation.release_session('target')
    assert failure.value.code == 'RECONCILIATION_REQUIRED'
    assert calls == [(None, 'target')]
