"""Pending publication work must not grow with terminal history."""
from types import SimpleNamespace
from contextlib import contextmanager

import pytest

from okto_nexus.bootstrap.embedded_dispatch import EmbeddedDispatchOwner
from okto_nexus.bootstrap.embedded_events import EmbeddedEventPublisher
from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery
from okto_nexus.bootstrap.embedded_retirement import EmbeddedRetirement
from okto_nexus.bootstrap.embedded_reconciliation import EmbeddedReconciliation
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from test_local_recovery_lookup import history


def pending_history(tmp_path, count, pending=3):
    reconciliation, factory, stats = history(tmp_path, count)
    with factory.unit_of_work() as uow:
        db = uow.connection
        db.executemany('INSERT INTO execution_local_publications '
            '(server_id,executor_id,operation_id,session_id,binding_json,terminal) '
            "VALUES('server','executor',?,?,'{}',?)",
            ((f'open-{i}', f'session-{i}', int(i < count-pending)) for i in range(count)))
        db.executemany('INSERT INTO execution_local_streams '
            '(server_id,executor_id,session_id,stream_epoch,opening_operation_id,binding_id,agent_id,drained) '
            "VALUES('server','executor',?,'epoch',?,'binding','agent',?)",
            ((f'session-{i}', f'open-{i}', int(i < count-pending)) for i in range(count)))
        # Synthetic already-retired history. This benchmark measures selection,
        # not proof validation; real retirement is covered by lifecycle tests.
        db.execute("UPDATE execution_sessions SET local_retirement_json='{\"version\":1}' "
            "WHERE session_id IN (SELECT session_id FROM execution_local_publications WHERE terminal=1)")
    owner = reconciliation.owner
    owner._after = 0
    return owner, EmbeddedEventPublisher(owner), factory, stats


@pytest.mark.parametrize('count', [1_000, 10_000, 100_000])
def test_pending_queries_have_bounded_cost_with_terminal_history(tmp_path, count, record_property):
    owner, events, factory, stats = pending_history(tmp_path, count)
    record_property('history_sessions', count)
    queries = {
        'publications': lambda: EmbeddedDispatchOwner._page(owner),
        'agent_publications': lambda: EmbeddedDispatchOwner._page(owner, agent_id='agent'),
        'streams': lambda: events._page(live_only=True),
        'agent_streams': lambda: events._page(agent_id='agent', live_only=True),
        'exact_session': lambda: events._page(session_id=f'session-{count-1}'),
        'unretired_streams': lambda: events._page(unretired_only=True),
        'pending_retirement': lambda: EmbeddedRetirement(owner).pending('agent'),
        'unretired_records': lambda: EmbeddedReconciliation(owner)._records(pending_only=True),
    }
    for name, query in queries.items():
        before = stats['steps']
        rows = query()
        assert len(rows) == (1 if name == 'exact_session' else 3)
        cost = stats['steps'] - before
        record_property(name + '_vm_steps', cost)
        assert cost < (1000 if name == 'unretired_records' else 500), (name, count, cost)
    before = stats['steps']
    assert EmbeddedAgentRecovery(owner)._pending_subjects() == {'agent'}
    record_property('pending_subjects_vm_steps', stats['steps'] - before)
    assert stats['steps'] - before < 500
    assert stats['verifications'] == len(queries) + 1
    # Also bound the actual retirement transaction's SQL work. These rows and
    # proof are synthetic; native proof production has separate lifecycle tests.
    target = f'session-{count-1}'
    with factory.unit_of_work(write=False) as uow:
        revision = uow.connection.execute('SELECT local_retirement_revision FROM execution_sessions '
            'WHERE session_id=?', (target,)).fetchone()[0]
    def instruction():
        stats['steps'] += 1
        return 0
    @contextmanager
    def measured_uow(*, write=True):
        with factory.unit_of_work(write=write) as uow:
            uow.connection.set_progress_handler(instruction, 1)
            try:
                yield uow
            finally:
                uow.connection.set_progress_handler(None, 0)
    owner.factory = SimpleNamespace(unit_of_work=measured_uow)
    before = stats['steps']
    assert EmbeddedRetirement(owner).commit(target, dict(server_id='server', executor_id='executor',
        session_id=target, opening_operation_id=f'open-{count-1}', owner_generation=1,
        stream_epoch='epoch', committed_sequence=0, retirement_revision=revision,
        release_kind='resource_released'))
    record_property('retirement_commit_vm_steps', stats['steps'] - before)
    assert stats['steps'] - before < 2000
    assert EmbeddedDispatchOwner._page(owner, agent_id='other') == []
    assert events._page(agent_id='other', live_only=True) == []
    assert events._page(session_id='missing') == []
    owner.channel.executor_id = 'other'
    assert EmbeddedDispatchOwner._page(owner) == []
    assert events._page(live_only=True) == []


def test_pending_membership_is_transactional_and_paging_preserves_all_rows(tmp_path):
    owner, events, factory, _ = pending_history(tmp_path, 300, pending=260)
    def all_rows(query):
        after, result = 0, []
        while rows := query(after=after):
            result.extend(r['session_id'] for r in rows)
            after = rows[-1]['rowid']
        return result
    publications = lambda **kw: EmbeddedDispatchOwner._page(owner, agent_id='agent', **kw)
    streams = lambda **kw: events._page(agent_id='agent', live_only=True, **kw)
    expected = [f'session-{i}' for i in range(40, 300)]
    assert all_rows(publications) == all_rows(streams) == expected
    # Rollback must retain membership; commit must remove both pending entries.
    for rollback in (True, False):
        try:
            with factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE execution_local_publications SET terminal=1 WHERE operation_id='open-40'")
                uow.connection.execute("UPDATE execution_local_streams SET drained=1 WHERE session_id='session-40'")
                if rollback:
                    raise RuntimeError('injected rollback')
        except RuntimeError:
            pass
        assert all_rows(publications) == all_rows(streams) == (expected if rollback else expected[1:])
    # Historical queries remain available for explicit audit and ACK replay.
    assert len(events._page(session_id='session-40')) == 1


@pytest.mark.asyncio
async def test_session_recovery_passes_exact_scope_to_storage():
    events = EmbeddedEventPublisher(SimpleNamespace())
    calls, visited = [], []
    def page(**kwargs):
        calls.append(kwargs)
        return [{'rowid': 7, 'session_id': 'target'}] if kwargs['after'] == 0 else []
    async def step(scope):
        visited.append(scope['session_id'])
        return False
    events._page, events.step = page, step
    await events.recover(agent_id='agent', session_id='target', live_only=True)
    assert visited == ['target']
    assert calls == [dict(after=after, agent_id='agent', session_id='target', live_only=True, unretired_only=True)
                     for after in (0, 7)]


def test_upgrade_builds_pending_indexes_from_existing_flags(tmp_path):
    owner, events, factory, _ = pending_history(tmp_path, 300, pending=2)
    names = ('idx_execution_local_publications_pending',
             'idx_execution_local_streams_pending', 'idx_execution_local_streams_agent_pending')
    with factory.unit_of_work() as uow:
        for name in names:
            uow.connection.execute(f'DROP INDEX {name}')
        uow.connection.execute('DELETE FROM schema_migrations WHERE version=143')
    MigrationRunner(factory).apply()
    MigrationRunner(factory).apply()  # Repeated startup does not rebuild or duplicate membership.
    assert len(EmbeddedDispatchOwner._page(owner)) == len(events._page(live_only=True)) == 2
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_local_streams').fetchone()[0] == 300
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_local_publications').fetchone()[0] == 300
        assert uow.connection.execute('SELECT COUNT(*) FROM schema_migrations WHERE version=143').fetchone()[0] == 1
