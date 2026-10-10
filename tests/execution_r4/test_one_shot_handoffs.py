from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, work, grant, claim
from test_canonical_result_publication import current_turn
from test_sender_sessions import configure, Peers, complete
from test_one_shot_runtime import query, wait_until


def test_managed_handoffs_share_capacity_and_keep_distinct_sessions(runtime):
    setup, binding, _ = runtime
    configure(setup, binding, 'one_shot')
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none' WHERE endpoint_id=?", (binding['endpoint_id'],))
    peers = Peers()
    setup[1].state.embedded_dispatch_owner.native_factory = peers
    first_handoff, second_handoff, gid = work(runtime), work(runtime), grant(runtime)
    first_claim = claim(runtime, first_handoff, gid, key='one-shot-first')
    assert first_claim['ok'], first_claim
    wait_until(setup, lambda: query(setup, "SELECT * FROM execution_operations WHERE action='turn.submit'"))
    first = current_turn(setup)
    wait_receipt(setup, first)
    second_claim = claim(runtime, second_handoff, gid, key='one-shot-second')
    assert second_claim['ok'], second_claim
    assert query(setup, "SELECT count(*) FROM one_shot_calls WHERE state='QUEUED'")[0][0] == 1
    complete(setup, peers, first, 'First handoff response')
    wait_until(setup, lambda: len(query(setup, 'SELECT * FROM execution_sessions')) == 2)
    calls = query(setup, 'SELECT state FROM one_shot_calls ORDER BY enqueued_at')
    assert calls[0]['state'] == 'SUCCEEDED'
    assert len({r[0] for r in query(setup, 'SELECT session_id FROM execution_sessions')}) == 2


def test_managed_handoff_queue_error_reaches_creator_inbox(runtime):
    from okto_nexus.application.one_shot_runtime import tick
    from okto_nexus.application.one_shot_notifications import publish_errors
    from okto_nexus.adapters.inbound.mcp.tools.harness import build_message_service
    setup, binding, _ = runtime
    configure(setup, binding, 'one_shot')
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none' WHERE endpoint_id=?", (binding['endpoint_id'],))
    first, second, gid = work(runtime), work(runtime), grant(runtime)
    assert claim(runtime, first, gid, key='hold-capacity')['ok']
    wait_until(setup, lambda: query(setup, "SELECT * FROM execution_operations WHERE action='turn.submit'"))
    wait_receipt(setup, current_turn(setup))
    assert claim(runtime, second, gid, key='expire-queued')['ok']
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE one_shot_calls SET queue_deadline=0 WHERE state='QUEUED'")
    tick(setup[0])
    publish_errors(setup[0], build_message_service(setup[0]))
    notice = query(setup, 'SELECT c.caller_id,m.body,d.recipient_agent_id FROM one_shot_calls c '
        'JOIN messages m ON m.message_id=c.notification_message_id JOIN message_deliveries d USING(message_id)')
    assert len(notice) == 1
    assert notice[0]['caller_id'] == notice[0]['recipient_agent_id'] == 'caller'
    assert 'ONE_SHOT_QUEUE_EXPIRED' in notice[0]['body']
    assert publish_errors(setup[0], build_message_service(setup[0])) == 0
