"""T34: ordinary broadcasts still fan out; directed handoffs wake only their target."""
import time

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, connect_local, wait_receipt
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime, call
from test_agent_recovery_isolation import create_agent
from test_handoff_runtime_candidates import enable_capacity
from test_runtime_policy_defaults import save
from test_sender_sessions import Peers, complete


def test_ordinary_broadcast_reaches_two_runtimes_and_mcp_but_direct_handoff_only_one(runtime):
    setup, first, _ = runtime
    deps, app, client, *_ = setup
    added, second, _ = connect_local(create_agent(setup, 'additional'), agent_id='additional')
    mcp_setup = create_agent(setup, 'mcp-only')
    mcp_runtime = (mcp_setup, first, None)
    registered = call(mcp_runtime, 'session_open', actor='subject', agent_id='mcp-only')
    assert registered['ok'], registered
    peers = Peers()
    app.state.embedded_dispatch_owner.native_factory = peers
    assert save(setup, session_policy='shared').status_code == 200
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='conversation',consumption='exclusive'")
    enable_capacity(runtime)
    made = call(runtime, 'message_create', from_agent_id='caller', target={'strategy': 'broadcast'},
                subject='Ordinary broadcast', body='Every eligible recipient should receive this')
    assert made['ok'], made
    mid = made['data']['message_id']
    deadline = time.monotonic() + 15
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            turns = [dict(row) for row in uow.connection.execute(
                "SELECT o.operation_id,o.session_id,d.recipient_agent_id FROM execution_operations o "
                "JOIN execution_domain_deliveries m USING(server_id,executor_id,operation_id) "
                "JOIN delivery_outbox d ON d.operation_id=m.domain_operation_id "
                "WHERE d.message_id=? AND o.action='turn.submit'", (mid,))]
        if len(turns) == 2:
            break
        assert time.monotonic() < deadline, turns
        time.sleep(.03)
    for turn in turns:
        wait_receipt(setup if turn['recipient_agent_id'] == 'subject' else added, turn)
    assert {turn['recipient_agent_id'] for turn in turns} == {'subject', 'additional'}
    assert len(peers.sessions) == 2 and all(len(peer.sent) == 1 for peer in peers.sessions.values())
    with deps.connection_factory.unit_of_work(write=False) as uow:
        deliveries = {row['recipient_agent_id']: row['consumer_kind'] for row in uow.connection.execute(
            'SELECT recipient_agent_id,consumer_kind FROM message_deliveries WHERE message_id=?', (mid,))}
        assert deliveries['subject'] == deliveries['additional'] == 'push'
        assert 'mcp-only' in deliveries and deliveries['mcp-only'] is None
    for turn in turns:
        complete(setup if turn['recipient_agent_id'] == 'subject' else added, peers, turn, 'Ordinary reply')
    direct = call(runtime, 'handoff_create', from_agent_id='caller', visibility='eligible',
                  target={'strategy': 'direct', 'agent_id': 'subject'}, payload='Directed handoff')
    assert direct['ok'], direct
    deadline = time.monotonic() + 15
    ids = [turn['operation_id'] for turn in turns]
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            extra = [dict(row) for row in uow.connection.execute(
                "SELECT operation_id,session_id,binding_id FROM execution_operations WHERE action='turn.submit' "
                'AND operation_id NOT IN (?,?)', ids)]
        if extra:
            break
        assert time.monotonic() < deadline
        time.sleep(.03)
    assert len(extra) == 1 and extra[0]['binding_id'] == first['binding_id']
    wait_receipt(setup, extra[0])
    assert len(peers.sessions) == 2 and sorted(len(peer.sent) for peer in peers.sessions.values()) == [1, 2]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute('SELECT 1 FROM handoff_runtime_attempts').fetchone()
        assert not uow.connection.execute('SELECT 1 FROM runtime_handoff_bindings').fetchone()
        assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?',
                                      (direct['data']['handoff_id'],)).fetchone()[:] == ('OPEN', 0)
