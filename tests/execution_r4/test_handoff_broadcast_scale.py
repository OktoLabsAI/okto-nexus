"""T01: 100 real configured candidates, bounded scheduler, one native winner.

Only the provider is synthetic. Agent/binding/grant APIs, discovery, capacity
ledger, canonical claim, dispatch and losing-reservation cleanup are real.
"""
import asyncio
import json
import time

from okto_nexus.bootstrap.handoff_runtime_scheduler import (
    build_handoff_runtime_candidates, build_handoff_runtime_scheduler,
)
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.domain.base import iso_plus
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, connect_local, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call
from test_agent_recovery_isolation import create_agent
from test_handoff_runtime_candidates import enable_capacity, lease
from test_runtime_policy_defaults import save
from test_sender_sessions import Peers


def test_hundred_runtime_candidates_have_one_winner_and_no_loser_native_invocation(runtime):
    setup, first, _ = runtime
    deps, app, client, headers, *_ = setup
    bindings, setups = {'subject': first}, {'subject': setup}
    for i in range(1, 100):
        actor = f'candidate-{i:03}'
        added, binding, _ = connect_local(create_agent(setup, actor), agent_id=actor)
        bindings[actor], setups[actor] = binding, added
        if i % 20 == 0:
            print(f'Configured {i + 1}/100 runtime candidates', flush=True)
    peers = Peers()
    app.state.embedded_dispatch_owner.native_factory = peers
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='none'")
    assert save(setup, broadcast_handoff_auto_claim=True).status_code == 200
    grants = []
    for actor, binding in bindings.items():
        response = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
            actor_agent_id=actor, endpoint_id=binding['endpoint_id'], actions=['execute_work'],
            max_executions=1, expires_at=iso_plus(deps.clock.now_iso(), 600)))
        assert response.status_code == 200, response.text
        grants.append(response.json()['data']['grant_id'])
    enable_capacity(runtime)
    owner = app.state.embedded_dispatch_owner
    async def published():
        async with asyncio.timeout(15):
            while True:
                host = deps.runtime_availability.current_host(owner.channel.server_id, owner.channel.executor_id)
                if host and {b['binding_id'] for b in bindings.values()} <= host.observations.keys():
                    return
                await asyncio.sleep(.02)
    client.portal.call(published)
    created = call(runtime, 'handoff_create', from_agent_id='caller', visibility='eligible',
                   target=dict(strategy='broadcast'), payload='One task, one runtime winner.')
    assert created['ok'], created
    hid = created['data']['handoff_id']
    discovery = build_handoff_runtime_candidates(deps)
    cursor, identities = '', []
    while True:
        page = discovery.prepare_page(lease(runtime, hid, cursor), limit=32)
        identities.extend(page.attempt_ids)
        cursor = page.cursor
        if not page.more:
            break
    assert len(identities) == len(set(identities)) == 100
    assert peers.sessions == {}
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(DISTINCT agent_id) FROM handoff_runtime_attempts').fetchone()[0] == 100
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
        # Availability notices exist for readers, but none entered the native queue.
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_pending_deliveries').fetchone()[0] == 0
    print('100 eligible candidates prepared; starting the bounded scheduler', flush=True)
    def settled():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT state FROM handoff_runtime_schedule WHERE handoff_id=?', (hid,)).fetchone()
            return row and row[0] == 'IDLE'
    async def compete():
        clock = [time.time()]
        scheduler = build_handoff_runtime_scheduler(deps, now=lambda: clock[0], monotonic=lambda: clock[0])
        try:
            async with asyncio.timeout(90):
                while not await asyncio.to_thread(settled):
                    scheduler.tick()
                    await asyncio.sleep(.05)
                    clock[0] += .5
        finally:
            assert await scheduler.aclose(timeout=10) == 0
    client.portal.call(compete)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        handoff = conn.execute('SELECT claimed_by,claim_epoch,status FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()
        winner = handoff['claimed_by']
        assert winner in bindings and tuple(handoff)[1:] == (1, 'CLAIMED')
        assert conn.execute('SELECT COUNT(*) FROM runtime_handoff_bindings WHERE handoff_id=?', (hid,)).fetchone()[0] == 1
        assert conn.execute('SELECT SUM(used_executions) FROM runtime_execution_grants '
                            'WHERE grant_id IN (SELECT value FROM json_each(?))',
                            (json.dumps(grants),)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM events WHERE type='handoff.claimed'").fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM execution_capacity_admissions').fetchone()[0] == 1
        active = conn.execute('SELECT agent_id,state FROM handoff_runtime_attempts WHERE active=1').fetchall()
        assert [tuple(row) for row in active] == [(winner, 'CLAIM_COMMITTED')]
        operations = conn.execute('SELECT operation_id,subject_agent_id,action FROM execution_operations').fetchall()
        assert len(operations) == 2 and {r['subject_agent_id'] for r in operations} == {winner}
        turn = next(dict(r) for r in operations if r['action'] == 'turn.submit')
    wait_receipt(setups[winner], turn)
    assert len(peers.sessions) == 1 and sum(len(p.sent) for p in peers.sessions.values()) == 1
    attempts = build_handoff_runtime_attempts(deps)
    port = client.portal.call(owner.execution_capacity)
    async def no_losing_reservations():
        states = []
        for identity in identities:
            attempt = await asyncio.to_thread(attempts.get, identity)
            result = await port.get_capacity_reservation(attempt.request)
            if attempt.principal.agent_id == winner:
                assert result and result.state == 'CONSUMED'
            else:
                assert result is None or result.state in ('RELEASED', 'EXPIRED_UNCONSUMED')
            if result:
                states.append(result.state)
        assert states.count('CONSUMED') == 1
    client.portal.call(no_losing_reservations)
    assert len(peers.sessions) == 1 and sum(len(p.sent) for p in peers.sessions.values()) == 1
