"""T19/T04: two broadcast tasks compete for one real physical opening slot."""
import asyncio

from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call
from test_handoff_automation_principal import prepare
from test_handoff_runtime_candidates import enable_capacity, lease
from test_sender_sessions import Peers, configure


def test_two_handoffs_race_for_one_slot_and_mcp_can_still_claim_the_waiting_task(runtime):
    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    peers = Peers()
    owner = app.state.embedded_dispatch_owner
    owner.native_factory = peers
    owner.host.max_owned_slots = 1
    # The capacity ledger is initialized during startup; changing only the
    # host field after that does not alter its durable admission policy.
    async def limit_existing_ledger():
        ledger = await owner.host._ledger()
        ledger.max_slots = 1
        await ledger._run(lambda db: db.execute(
            'INSERT INTO owned_slot_policy(singleton,max_slots) VALUES(1,1) '
            'ON CONFLICT(singleton) DO UPDATE SET max_slots=1'))
    client.portal.call(limit_existing_ledger)
    configure(setup, binding, 'per_sender_session')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none' WHERE endpoint_id=?", (binding['endpoint_id'],))
    sources = [call(runtime, 'session_open', agent_id='caller') for _ in range(2)]
    assert all(result['ok'] for result in sources)
    origins = [{name: result['data'][name] for name in ('session_id','session_secret')} for result in sources]
    _, first, grant = prepare(runtime, **origins[0])
    made = call(runtime, 'handoff_create', from_agent_id='caller', visibility='eligible',
                target=dict(strategy='broadcast'), payload='Second independent task', **origins[1])
    assert made['ok'], made
    handoffs = [first, made['data']['handoff_id']]
    enable_capacity(runtime)
    discovery, attempts = build_handoff_runtime_candidates(deps), build_handoff_runtime_attempts(deps)
    ids = [discovery.prepare_page(lease(runtime, hid), limit=4).attempt_ids[0] for hid in handoffs]
    assert len({attempts.get(identity).request.affinity_key for identity in ids}) == 2
    async def compete():
        return await asyncio.gather(*(attempts.reserve(identity) for identity in ids))
    results = client.portal.call(compete)
    assert sorted(result.state for result in results) == ['NOT_AVAILABLE','RESERVED']
    winner = next(result for result in results if result.state == 'RESERVED')
    loser = next(result for result in results if result.state == 'NOT_AVAILABLE')
    assert loser.reason == 'HOST_FULL'
    # A refusal after reserve was sent is not a durable tombstone: an earlier
    # in-flight retry may still reserve. Release must fence that exact identity.
    cleaned = client.portal.call(attempts.release, loser.request.attempt_id)
    assert not cleaned.active and cleaned.reservation.state == 'RELEASED'
    assert peers.sessions == {}
    committed = attempts.claim(winner.request.attempt_id)
    transferred = client.portal.call(build_capacity_admission(deps).consume, committed.operation_id)
    wait_receipt(setup, dict(operation_id=transferred.consumption.turn_operation_id))
    assert len(peers.sessions) == 1 and sum(len(p.sent) for p in peers.sessions.values()) == 1
    winning_hid = handoffs[ids.index(winner.request.attempt_id)]
    late = call(runtime, 'handoff_claim', actor='operator', agent_id='operator', handoff_id=winning_hid)
    assert not late['ok'] and late['error']['code'] == 'HANDOFF_ALREADY_CLAIMED', late
    losing_hid = handoffs[ids.index(loser.request.attempt_id)]
    offered = call(runtime, 'handoff_list_available', actor='operator', agent_id='operator')
    assert offered['ok'] and losing_hid in str(offered['data']), offered
    explicit = call(runtime, 'handoff_claim', actor='operator', agent_id='operator', handoff_id=losing_hid)
    assert explicit['ok'], explicit
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 2
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_bindings').fetchone()[0] == 1
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (grant,)).fetchone()[0] == 1
        assert uow.connection.execute('SELECT claimed_by FROM handoffs WHERE handoff_id=?', (losing_hid,)).fetchone()[0] == 'operator'
    assert len(peers.sessions) == 1 and sum(len(p.sent) for p in peers.sessions.values()) == 1
