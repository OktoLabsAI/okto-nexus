"""The scheduler resumes durable attempts through the real claim/host path."""
import asyncio

import pytest

from okto_nexus.application.handoff_runtime_processor import HandoffCandidatePage
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_scheduler
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime
from test_handoff_runtime_attempts import prepared
from test_canonical_result_publication import current_turn


@pytest.mark.parametrize('committed_before_restart', [False, True])
def test_schedule_sweep_resumes_exact_attempt_and_consumption_after_lost_reply(runtime, committed_before_restart):
    setup, _, native = runtime
    deps, _, client, *_ = setup
    attempts, port, attempt, hid, gid = prepared(runtime)
    aid = attempt.request.attempt_id
    if committed_before_restart:
        client.portal.call(attempts.reserve, aid)
        attempts.claim(aid)
    assert native.opens == 0

    class Candidates:
        # This campaign begins with a persisted candidate to isolate scheduler
        # recovery. Automatic discovery/preparation has its own integration gate.
        def prepare_page(self, lease, *, limit):
            assert lease.handoff_id == hid and lease.claim_generation == 0 and limit == 4
            with deps.connection_factory.unit_of_work(write=False) as uow:
                row = uow.connection.execute('SELECT a.operation_id,c.state FROM handoff_runtime_attempts a '
                    'LEFT JOIN execution_capacity_admissions c ON c.domain_operation_id=a.operation_id '
                    'WHERE a.attempt_id=?', (aid,)).fetchone()
            if row['operation_id'] and row['state'] == 'CONSUMED':
                return HandoffCandidatePage((), settled=True)
            return HandoffCandidatePage((aid,))

    class LoseConsumeReply:
        consumed = None
        calls = 0

        def __getattr__(self, name):
            return getattr(port, name)

        async def consume_capacity(self, req, reservation_id, consumption):
            self.calls += 1
            result = await port.consume_capacity(req, reservation_id, consumption)
            if self.consumed is None:
                self.consumed = result
                raise TimeoutError('Consumed before a lost response')
            assert result.reservation_id == self.consumed.reservation_id
            assert result.consumption == self.consumed.consumption
            return result

    adapter = LoseConsumeReply()
    clock = [100.]

    def record():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute('SELECT state,reason FROM handoff_runtime_schedule WHERE handoff_id=?', (hid,)).fetchone()

    async def wait_for(predicate):
        async with asyncio.timeout(10):
            while not predicate():
                await asyncio.sleep(.01)

    async def run():
        scheduler = build_handoff_runtime_scheduler(deps, candidates=Candidates(), capacity=adapter,
            max_running=2, scan_limit=4, now=lambda: clock[0], monotonic=lambda: clock[0])
        scheduler.tick()
        await wait_for(lambda: record() is not None and record()['reason'] == 'NEEDS_RECONCILIATION')
        assert await scheduler.aclose(timeout=5) == 0
        assert adapter.calls == 1
        # Reconstruct from the same DB: no new attempt, claim epoch or operation.
        clock[0] += 6
        scheduler = build_handoff_runtime_scheduler(deps, candidates=Candidates(), capacity=adapter,
            max_running=2, scan_limit=4, now=lambda: clock[0], monotonic=lambda: clock[0])
        try:
            scheduler.tick()
            await wait_for(lambda: record()['reason'] == 'CLAIM_COMMITTED' and scheduler.pending_count == 0)
            clock[0] += 6
            scheduler.tick()
            await wait_for(lambda: record()['state'] == 'IDLE' and scheduler.pending_count == 0)
        finally:
            assert await scheduler.aclose(timeout=5) == 0

    client.portal.call(run)
    wait_receipt(setup, current_turn(setup))
    assert adapter.calls == 2
    assert native.opens == len(native.native.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM handoff_runtime_attempts').fetchone()[0] == 1
        assert uow.connection.execute('SELECT count(*) FROM runtime_handoff_bindings').fetchone()[0] == 1
        assert uow.connection.execute('SELECT claim_epoch,status FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == (1, 'CLAIMED')
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,)).fetchone()[0] == 1
        assert uow.connection.execute('SELECT count(*) FROM handoff_runtime_schedule').fetchone()[0] == 1
