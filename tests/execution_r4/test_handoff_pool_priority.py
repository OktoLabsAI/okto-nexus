"""T38: automatic work cannot jump prior one-shot consumers across recovery."""
import asyncio
import time

import pytest

from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_scheduler
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call
from test_handoff_automation_principal import prepare
from test_handoff_runtime_candidates import enable_capacity
from test_one_shot_runtime import query, wait_until
from test_sender_sessions import Peers, configure, turn_for, complete


@pytest.mark.parametrize('recreate_scheduler', [False, True])
def test_automatic_handoff_preserves_one_shot_fifo_before_and_after_scheduler_recovery(runtime, recreate_scheduler):
    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    peers = Peers()
    app.state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'one_shot')

    def message(text):
        made = call(runtime, 'message_create', from_agent_id='caller',
            target={'strategy': 'direct', 'agent_id': 'subject'}, subject='Pool priority', body=text)
        assert made['ok'], made
        return made['data']['message_id']

    first = turn_for(setup, message('First already running'))
    wait_receipt(setup, first)
    second_id, third_id = message('Second in queue'), message('Third in queue')
    assert query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='QUEUED'")[0][0] == 2
    _, hid, gid = prepare(runtime)
    enable_capacity(runtime)
    clock = [time.time()]

    def new_scheduler():
        return build_handoff_runtime_scheduler(deps, now=lambda: clock[0], monotonic=lambda: clock[0])

    scheduler = new_scheduler()

    async def round_once():
        clock[0] += 20
        async with asyncio.timeout(15):
            while True:
                scheduler.tick()
                await asyncio.sleep(.02)
                rows = query(setup, 'SELECT state,reason,due_at,lease_until FROM handoff_runtime_schedule WHERE handoff_id=?', (hid,))
                if rows and rows[0]['lease_until'] == 0 and (rows[0]['state'] == 'IDLE' or rows[0]['due_at'] > clock[0]):
                    return rows[0]['reason']

    def still_unclaimed():
        assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('OPEN', 0)
        assert query(setup, 'SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,))[0][0] == 0
        assert not query(setup, 'SELECT 1 FROM runtime_handoff_bindings WHERE handoff_id=?', (hid,))
        assert query(setup, 'SELECT count(*) FROM one_shot_calls')[0][0] == 3

    try:
        assert client.portal.call(round_once) == 'EARLIER_WORK_PENDING'
        still_unclaimed()
        if recreate_scheduler:
            assert client.portal.call(scheduler.aclose) == 0
            scheduler = new_scheduler()
            assert client.portal.call(round_once) == 'EARLIER_WORK_PENDING'
            still_unclaimed()
        complete(setup, peers, first, 'First done')
        second = turn_for(setup, second_id)
        wait_receipt(setup, second)
        assert client.portal.call(round_once) == 'EARLIER_WORK_PENDING'
        still_unclaimed()
        assert query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='QUEUED'")[0][0] == 1
        complete(setup, peers, second, 'Second done')
        third = turn_for(setup, third_id)
        wait_receipt(setup, third)
        assert client.portal.call(round_once) in {'POOL_FULL', 'HOST_FULL'}
        still_unclaimed()
        complete(setup, peers, third, 'Third done')
        wait_until(setup, lambda: not query(setup, 'SELECT 1 FROM one_shot_slots'))
        # A completed page reports SETTLED; canonical ownership and the actual
        # turn below establish execution, not the scheduler diagnostic label.
        assert client.portal.call(round_once) in {'CLAIM_COMMITTED', 'SETTLED'}
        operation = query(setup, 'SELECT operation_id FROM runtime_handoff_bindings WHERE handoff_id=?', (hid,))[0][0]
        turn = query(setup, "SELECT p.operation_id,p.session_id FROM execution_operations p JOIN execution_domain_deliveries d "
            "USING(server_id,executor_id,operation_id) WHERE d.domain_operation_id=? AND p.action='turn.submit'", (operation,))[0]
        wait_receipt(setup, dict(turn))
        assert query(setup, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == ('CLAIMED', 1)
        assert query(setup, 'SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,))[0][0] == 1
        assert len(peers.sessions) == 4
        assert [row[0] for row in query(setup, 'SELECT call_id FROM one_shot_calls ORDER BY started_at')] == [
            row[0] for row in query(setup, 'SELECT call_id FROM one_shot_calls ORDER BY enqueued_at,call_id')]
        assert all(len(peer.sent) == 1 for peer in peers.sessions.values())
    finally:
        assert client.portal.call(scheduler.aclose) == 0
