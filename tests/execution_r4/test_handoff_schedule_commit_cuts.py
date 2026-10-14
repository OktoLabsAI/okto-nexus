"""T24: scheduling cursor, wake and token writes share their commit boundary."""
import pytest

from okto_nexus.application.handoff_runtime_scheduler import HandoffRuntimeScheduler, HandoffScheduleOutcome
from test_handoff_runtime_scheduler import schedule, seed, rows
from test_handoff_recovery_commit_cuts import cut_transition


@pytest.mark.parametrize('boundary', ['rollback', 'lost_reply'])
@pytest.mark.parametrize('stage', ['scan_lease', 'renew', 'finish'])
def test_schedule_commit_cut_recovers_cursor_wake_and_fences_old_owner(schedule, boundary, stage):
    factory, repo = schedule
    seed(schedule, 2)
    clock = [10]
    scheduler = HandoffRuntimeScheduler(factory=factory, repository=repo, processor=None,
        scan_limit=2, lease_seconds=5, now=lambda: clock[0])

    def scan():
        with factory.unit_of_work(write=False) as uow:
            return dict(uow.connection.execute('SELECT * FROM handoff_runtime_schedule_scan').fetchone())

    before_scan = scan()
    if stage == 'scan_lease':
        fired = cut_transition(scheduler,
            lambda uow: uow.connection.execute('SELECT count(*) FROM handoff_runtime_schedule').fetchone()[0],
            2, boundary)
        with pytest.raises(OSError):
            scheduler._reserve_page(True, True, (), 2)
        assert fired == [2]
        if boundary == 'rollback':
            assert rows(schedule) == [] and scan() == before_scan
        else:
            assert len(rows(schedule)) == 2
            assert scan()['handoff_cursor'] == 2
            assert scan()['wake_generation'] == before_scan['wake_generation'] + 1
            assert all(row['lease_until'] == 15 for row in rows(schedule))
        # A lost lease reply cannot launch work; only expiry permits a new
        # scanner. The durable agenda still has one row per canonical epoch.
        clock[0] = 16
        restarted = HandoffRuntimeScheduler(factory=factory, repository=repo, processor=None,
            scan_limit=2, lease_seconds=5, now=lambda: clock[0])
        leases = restarted._reserve_page(False, True, (), 2)
        assert {lease.handoff_id for lease in leases} == {'h000', 'h001'}
        assert len(rows(schedule)) == 2
        assert all(lease.claim_generation == 0 for lease in leases)
        return

    lease, _ = scheduler._reserve_page(False, True, (), 2)
    if stage == 'renew':
        clock[0] = 11
        target = 16
        state = lambda uow: uow.connection.execute(
            'SELECT lease_until FROM handoff_runtime_schedule WHERE handoff_id=?', (lease.handoff_id,)).fetchone()[0]
        action = lambda: scheduler._reserve_page(False, False, (lease,), 0)
    else:
        target = 'agent-b'
        state = lambda uow: uow.connection.execute(
            'SELECT candidate_cursor FROM handoff_runtime_schedule WHERE handoff_id=?', (lease.handoff_id,)).fetchone()[0]
        outcome = HandoffScheduleOutcome('MORE_CANDIDATES', 'agent-b')
        action = lambda: scheduler._finish(lease, outcome)
    fired = cut_transition(scheduler, state, target, boundary)
    with pytest.raises(OSError):
        action()
    assert fired == [target]
    after = next(row for row in rows(schedule) if row['handoff_id'] == lease.handoff_id)
    if stage == 'renew':
        assert after['lease_until'] == (15 if boundary == 'rollback' else 16)
        assert after['lease_token'] == lease.token
    else:
        assert after['candidate_cursor'] == ('' if boundary == 'rollback' else 'agent-b')
        assert after['backoff_count'] == int(boundary == 'lost_reply')
    scheduler.factory = factory
    action()  # Exact original token; a committed finish cannot apply twice.
    settled = next(row for row in rows(schedule) if row['handoff_id'] == lease.handoff_id)
    if stage == 'finish':
        assert settled['candidate_cursor'] == 'agent-b' and settled['backoff_count'] == 1
        assert settled['lease_token'] is None
    clock[0] = 20
    with factory.unit_of_work() as uow:
        newer = repo.lease_due(uow, now=20, limit=2, lease_seconds=5)
        replacement = next(item for item in newer if item.handoff_id == lease.handoff_id)
        assert replacement.token != lease.token
        assert not repo.renew(uow, lease, now=21, lease_seconds=5)
        assert not repo.finish(uow, lease, HandoffScheduleOutcome('SETTLED', done=True), now=21)
    assert len(rows(schedule)) == 2
