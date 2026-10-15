"""T11: a third authenticated creator session is independent of two busy ones."""
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from okto_nexus.domain.base import iso_plus
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call
from test_handoff_runtime_candidates import enable_capacity, lease
from test_runtime_policy_defaults import save
from test_sender_sessions import Peers, configure


def test_third_creator_session_executes_while_two_other_sources_remain_busy(runtime):
    setup, binding, _ = runtime
    deps, app, client, headers, *_ = setup
    peers = Peers()
    app.state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'per_sender_session')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none' WHERE endpoint_id=?", (binding['endpoint_id'],))
    assert save(setup, agent='subject', broadcast_handoff_auto_claim=True).status_code == 200
    grant = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
        actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=['execute_work'],
        max_executions=4, expires_at=iso_plus(deps.clock.now_iso(), 600)))
    assert grant.status_code == 200, grant.text
    enable_capacity(runtime)
    discovery, attempts = build_handoff_runtime_candidates(deps), build_handoff_runtime_attempts(deps)
    transfer = build_capacity_admission(deps)
    sources, winners = [], []
    def candidate(source):
        made = call(runtime, 'handoff_create', from_agent_id='caller', visibility='eligible',
                    target=dict(strategy='broadcast'), payload='Isolated source work',
                    session_id=source['session_id'], session_secret=source['session_secret'])
        assert made['ok'], made
        hid = made['data']['handoff_id']
        page = discovery.prepare_page(lease(runtime, hid), limit=4)
        assert len(page.attempt_ids) == 1
        return attempts.get(page.attempt_ids[0])
    for i in range(3):
        opened = call(runtime, 'session_open', agent_id='caller')
        assert opened['ok'], opened
        sources.append(opened['data'])
        attempt = candidate(sources[-1])
        assert attempt.request.unit == 'new_session'
        assert len(peers.sessions) == i
        assert client.portal.call(attempts.reserve, attempt.request.attempt_id).state == 'RESERVED'
        claimed = attempts.claim(attempt.request.attempt_id)
        consumed = client.portal.call(transfer.consume, claimed.operation_id)
        wait_receipt(setup, dict(operation_id=consumed.consumption.turn_operation_id))
        winners.append(attempt)
        assert len(peers.sessions) == i+1 and all(len(p.sent) == 1 for p in peers.sessions.values())
        # The old source remains busy even though another source can open.
        busy = candidate(sources[0])
        assert busy.request.unit == 'next_turn'
        assert busy.request.scope.session_id == winners[0].request.scope.session_id
        refused = client.portal.call(attempts.reserve, busy.request.attempt_id)
        assert refused.state == 'NOT_AVAILABLE' and refused.reason in ('BUSY_AFFINITY', 'EARLIER_WORK_PENDING')
    assert len({a.request.affinity_key for a in winners}) == 3
    assert len({a.request.scope.session_id for a in winners}) == 3
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM handoffs WHERE status='CLAIMED'").fetchone()[0] == 3
        assert uow.connection.execute("SELECT COUNT(*) FROM handoffs WHERE status='OPEN'").fetchone()[0] == 3
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?',
            (grant.json()['data']['grant_id'],)).fetchone()[0] == 3
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_receipts r JOIN execution_operations o "
            "USING(server_id,executor_id,operation_id) WHERE r.stage IN ('SUCCEEDED','FAILED','CANCELLED') "
            "AND o.action IN ('turn.submit','turn.steer')").fetchone()[0] == 0
