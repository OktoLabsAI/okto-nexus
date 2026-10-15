"""Durable paging, fencing, wakeups and bounded producers over real SQLite."""
import asyncio
from collections import Counter
import json
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.adapters.outbound.sqlite.handoff_runtime_schedule import SqliteHandoffScheduleRepository
from okto_nexus.application.handoff_runtime_scheduler import HandoffRuntimeScheduler, HandoffScheduleOutcome
from okto_nexus.config import NexusConfig


@pytest.fixture
def schedule(tmp_path):
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path / 'home'))
    MigrationRunner(factory).apply()
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES('w','2026-01-01')")
    return factory, SqliteHandoffScheduleRepository()


def seed(schedule, count, *, direct=False):
    factory, _ = schedule
    with factory.unit_of_work() as uow:
        for n in range(count):
            target = {'strategy': 'direct', 'agent_id': 'agent'} if direct else {'strategy': 'broadcast'}
            uow.connection.execute("INSERT INTO handoffs(handoff_id,workspace_id,target,status,created_at) VALUES(?,'w',?,'OPEN','2026-01-01')",
                                   (('d' if direct else 'h') + str(n).zfill(3), json.dumps(target)))


def rows(schedule):
    with schedule[0].unit_of_work(write=False) as uow:
        return [dict(r) for r in uow.connection.execute('SELECT * FROM handoff_runtime_schedule ORDER BY handoff_id,claim_generation')]


async def until(predicate):
    async with asyncio.timeout(5):
        while not predicate():
            await asyncio.sleep(.005)


def test_fallback_scan_has_durable_bounded_cursors_and_one_row_per_generation(schedule):
    seed(schedule, 101)
    seed(schedule, 3, direct=True)
    factory, repo = schedule
    with factory.unit_of_work() as uow:
        assert repo.sweep(uow, now=10, limit=7) == (7, 0)
    assert len(rows(schedule)) == 7
    # New repository instances resume the persisted scan, not the first page.
    for _ in range(14):
        with factory.unit_of_work() as uow:
            scanned = SqliteHandoffScheduleRepository().sweep(uow, now=11, limit=7)
            assert scanned[0] <= 7 and scanned[1] <= 7
    assert len(rows(schedule)) == 101
    with factory.unit_of_work() as uow:
        assert uow.connection.execute('SELECT handoff_cursor FROM handoff_runtime_schedule_scan').fetchone()[0] == 0
        uow.connection.execute("UPDATE handoffs SET claim_epoch=1 WHERE handoff_id='h000'")
        repo.notify(uow, handoff_id='h000', now=12)
        repo.notify(uow, handoff_id='h000', now=12)
        repo.notify(uow, handoff_id='d000', now=12)
    assert len(rows(schedule)) == 102
    assert [r['claim_generation'] for r in rows(schedule) if r['handoff_id'] == 'h000'] == [0, 1]


@pytest.mark.parametrize('change', ['defaults', 'override', 'agent'])
def test_policy_change_wakes_backoff_durably_but_presence_does_not(schedule, change):
    seed(schedule, 1)
    factory, repo = schedule
    with factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agents(agent_id,created_at) VALUES('agent','2026-01-01')")
        repo.sweep(uow, now=10, limit=1)
        leased, = repo.lease_due(uow, now=10, limit=1, lease_seconds=5)
        repo.finish(uow, leased, HandoffScheduleOutcome('NOT_AUTHORIZED'), now=10)
        before = uow.connection.execute('SELECT wake_generation FROM handoff_runtime_schedule_scan').fetchone()[0]
        uow.connection.execute("UPDATE agents SET last_seen_at='2026-01-02' WHERE agent_id='agent'")
        assert uow.connection.execute('SELECT wake_generation FROM handoff_runtime_schedule_scan').fetchone()[0] == before
        assert repo.lease_due(uow, now=11, limit=1, lease_seconds=5) == ()
        if change == 'defaults':
            uow.connection.execute('UPDATE runtime_policy_defaults SET broadcast_handoff_auto_claim=1')
        elif change == 'override':
            uow.connection.execute("INSERT INTO agent_runtime_overrides(agent_id,broadcast_handoff_auto_claim,revision) VALUES('agent',1,1)")
        else:
            uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='agent'")
    with factory.unit_of_work() as uow:
        renewed, = SqliteHandoffScheduleRepository().lease_due(uow, now=11, limit=1, lease_seconds=5)
        assert renewed.wake_generation > before
        assert renewed.token != leased.token


def test_historical_unknown_targets_do_not_become_competitive_or_break_lifecycle_events(schedule):
    factory, repo = schedule
    with factory.unit_of_work() as uow:
        for n, target in enumerate((None, 'legacy-unknown', '[]')):
            hid = f'historical-{n}'
            uow.connection.execute("INSERT INTO handoffs(handoff_id,workspace_id,target,status,created_at) VALUES(?,'w',?,'CANCELLED','2026-01-01')",
                                   (hid, target))
            repo.notify(uow, handoff_id=hid, now=10)
    assert rows(schedule) == []


def test_expired_scanner_cannot_overwrite_new_owner_cursor_or_backoff(schedule):
    seed(schedule, 1)
    factory, repo = schedule
    with factory.unit_of_work() as uow:
        repo.sweep(uow, now=10, limit=8)
        old, = repo.lease_due(uow, now=10, limit=1, lease_seconds=5)
    with factory.unit_of_work() as uow:
        assert repo.lease_due(uow, now=14, limit=1, lease_seconds=5) == ()
        current, = repo.lease_due(uow, now=16, limit=1, lease_seconds=5)
        assert current.token != old.token
        assert not repo.finish(uow, old, HandoffScheduleOutcome('SETTLED', done=True), now=16)
        assert not repo.renew(uow, old, now=16, lease_seconds=5)
        assert repo.finish(uow, current, HandoffScheduleOutcome('BUSY_AFFINITY', 'agent-b'), now=16)
    assert rows(schedule)[0]['due_at'] == 17
    with factory.unit_of_work() as uow:
        assert SqliteHandoffScheduleRepository().lease_due(uow, now=16.5, limit=1, lease_seconds=5) == ()
        resumed, = repo.lease_due(uow, now=17, limit=1, lease_seconds=5)
        assert resumed.candidate_cursor == 'agent-b'
        repo.finish(uow, resumed, HandoffScheduleOutcome('BUSY_AFFINITY', 'agent-c'), now=17)
    assert rows(schedule)[0]['due_at'] == 19


def test_historical_and_directed_rows_do_not_delay_recovery_of_open_broadcast(schedule):
    seed(schedule, 301)
    seed(schedule, 300, direct=True)
    factory, repo = schedule
    with factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET status='COMPLETED' WHERE handoff_id LIKE 'h%' AND handoff_id<'h300'")
        assert repo.sweep(uow, now=10, limit=4) == (1, 0)
    assert [r['handoff_id'] for r in rows(schedule)] == ['h300']


def test_database_reset_keeps_the_scan_seed_and_recovers_new_work(schedule):
    from okto_nexus.application.database_reset import clear_operational_history
    seed(schedule, 1)
    factory, repo = schedule
    with factory.unit_of_work() as uow:
        repo.sweep(uow, now=1, limit=1)
        assert uow.connection.execute('SELECT handoff_cursor FROM handoff_runtime_schedule_scan').fetchone()[0] > 0
        clear_operational_history(uow.connection, keep_agents=True)
        assert uow.connection.execute('SELECT handoff_cursor,attempt_cursor FROM handoff_runtime_schedule_scan').fetchone()[:] == (0, 0)
    assert rows(schedule) == []
    seed(schedule, 1)
    with factory.unit_of_work() as uow:
        repo.sweep(uow, now=2, limit=2)
        assert len(repo.lease_due(uow, now=2, limit=1, lease_seconds=10)) == 1


def test_wakeup_during_lease_is_not_lost_and_sweep_preserves_pending_backoff(schedule):
    seed(schedule, 1)
    factory, repo = schedule
    with factory.unit_of_work() as uow:
        repo.notify(uow, handoff_id='h000', now=1)
        active, = repo.lease_due(uow, now=1, limit=1, lease_seconds=20)
        repo.notify(uow, handoff_id='h000', now=2)
        repo.finish(uow, active, HandoffScheduleOutcome('SETTLED', done=True), now=3)
    assert rows(schedule)[0]['state'] == 'PENDING' and rows(schedule)[0]['due_at'] == 3
    with factory.unit_of_work() as uow:
        active, = repo.lease_due(uow, now=3, limit=1, lease_seconds=20)
        repo.finish(uow, active, HandoffScheduleOutcome('CAPACITY_PROTOCOL_UNSUPPORTED'), now=3)
        repo.sweep(uow, now=4, limit=2)
        assert repo.lease_due(uow, now=4, limit=1, lease_seconds=20) == ()
        repo.wake(uow)  # Global capacity/policy signal bypasses the old backoff.
        active, = repo.lease_due(uow, now=4, limit=1, lease_seconds=20)
        repo.wake(uow)  # A second signal lands while the processor is working.
        repo.finish(uow, active, HandoffScheduleOutcome('BUSY_AFFINITY'), now=4)
        assert len(repo.lease_due(uow, now=4, limit=1, lease_seconds=20)) == 1


def test_slow_work_retains_one_slot_while_other_handoffs_and_close_progress(schedule):
    seed(schedule, 3)
    factory, repo = schedule

    async def run():
        release, entered = asyncio.Event(), asyncio.Event()
        calls = Counter()

        async def process(lease):
            calls[lease.handoff_id] += 1
            if lease.handoff_id == 'h000':
                entered.set()
                await release.wait()
            return HandoffScheduleOutcome('SETTLED', done=True)

        scheduler = HandoffRuntimeScheduler(factory=factory, repository=repo,
            processor=SimpleNamespace(process=process), max_running=2, scan_limit=3,
            now=lambda: 100, monotonic=lambda: 0)
        try:
            for _ in range(100):
                scheduler.wake()
            scheduler.tick()
            await asyncio.wait_for(entered.wait(), 5)
            await until(lambda: calls['h001'] == 1 and len(scheduler._running) == 1)
            scheduler.tick()
            await until(lambda: calls['h002'] == 1 and len(scheduler._running) == 1)
            assert calls == {'h000': 1, 'h001': 1, 'h002': 1}
            with factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT wake_generation FROM handoff_runtime_schedule_scan').fetchone()[0] == 1
            assert await scheduler.aclose(timeout=.001) == 1
            for _ in range(100):
                scheduler.wake()
                scheduler.tick()
            assert scheduler.pending_count == 1 and calls['h000'] == 1
        finally:
            release.set()
            assert await scheduler.aclose(timeout=5) == 0
        assert all(r['state'] == 'IDLE' for r in rows(schedule))
    asyncio.run(run())


def test_processor_exception_is_retained_as_uncertainty_with_durable_retry(schedule):
    seed(schedule, 1)
    factory, repo = schedule

    async def run():
        async def failed(lease):
            raise OSError('private-error-detail')
        scheduler = HandoffRuntimeScheduler(factory=factory, repository=repo,
            processor=SimpleNamespace(process=failed), max_running=1, now=lambda: 10, monotonic=lambda: 0)
        scheduler.tick()
        await until(lambda: rows(schedule) and rows(schedule)[0]['reason'] == 'NEEDS_RECONCILIATION')
        assert await scheduler.aclose(timeout=5) == 0
        row, = rows(schedule)
        assert row['state'] == 'PENDING' and row['due_at'] == 15
        assert 'private-error-detail' not in str(row)
        with factory.unit_of_work() as uow:
            assert repo.lease_due(uow, now=14, limit=1, lease_seconds=5) == ()
            assert len(repo.lease_due(uow, now=15, limit=1, lease_seconds=5)) == 1
    asyncio.run(run())
