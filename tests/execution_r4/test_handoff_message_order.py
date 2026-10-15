"""T08/T38: busy sender work preserves ordinary message FIFO before auto-claim."""
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call
from test_handoff_automation_principal import prepare
from test_handoff_runtime_candidates import enable_capacity, lease
from test_sender_sessions import Peers, configure, turn_for, complete


def test_busy_sender_broadcast_waits_for_existing_direct_message_order(runtime):
    setup, binding, _ = runtime
    deps, app, client, *_ = setup
    peers = Peers()
    app.state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'per_sender')
    _, hid, gid = prepare(runtime)
    enable_capacity(runtime)
    discovery = build_handoff_runtime_candidates(deps)
    attempts = build_handoff_runtime_attempts(deps)

    def message(text):
        made = call(runtime, 'message_create', from_agent_id='caller',
            target={'strategy': 'direct', 'agent_id': 'subject'}, subject='FIFO', body=text)
        assert made['ok'], made
        return turn_for(setup, made['data']['message_id'])

    first = message('First running message')
    wait_receipt(setup, first)
    second, third = message('Second queued message'), message('Third queued message')
    assert {turn['session_id'] for turn in (first, second, third)} == {first['session_id']}

    def refused():
        page = discovery.prepare_page(lease(runtime, hid), limit=4)
        assert len(page.attempt_ids) == 1, page
        attempt = client.portal.call(attempts.reserve, page.attempt_ids[0])
        assert attempt.state == 'NOT_AVAILABLE'
        assert attempt.reason in {'BUSY_AFFINITY', 'EARLIER_WORK_PENDING'}
        assert not client.portal.call(attempts.release, page.attempt_ids[0]).active
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('OPEN', 0)
            assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,)).fetchone()[0] == 0
            assert not uow.connection.execute('SELECT 1 FROM runtime_handoff_bindings').fetchone()

    refused()
    peer = peers.sessions[first['session_id']]
    assert peer.sent == [('send_turn', first['operation_id'])]
    complete(setup, peers, first, 'First complete')
    wait_receipt(setup, second)
    refused()
    assert peer.sent == [('send_turn', turn['operation_id']) for turn in (first, second)]
    complete(setup, peers, second, 'Second complete')
    wait_receipt(setup, third)
    refused()
    complete(setup, peers, third, 'Third complete')

    page = discovery.prepare_page(lease(runtime, hid), limit=4)
    held = client.portal.call(attempts.reserve, page.attempt_ids[0])
    assert held.state == 'RESERVED'
    assert held.request.scope.session_id == first['session_id']
    committed = attempts.claim(page.attempt_ids[0])
    admitted = client.portal.call(build_capacity_admission(deps).consume, committed.operation_id)
    wait_receipt(setup, {'operation_id': admitted.consumption.turn_operation_id})
    assert len(peers.sessions) == 1
    assert peer.sent == [('send_turn', turn['operation_id']) for turn in (first, second, third)] + [
        ('send_turn', admitted.consumption.turn_operation_id)]
