"""Managed execution inherits its creator's verified origin, not the claimant's."""
import json
from pathlib import Path
import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local
from test_sender_sessions import configure, Peers
from okto_nexus.domain.base import iso_plus


@pytest.mark.parametrize('origin_write_fails', [False, True])
def test_distinct_creator_sessions_select_distinct_managed_handoff_sessions(connected_local, monkeypatch, origin_write_fails):
    setup, binding, _ = connected_local
    deps, app, client, headers, *_ = setup
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    client.headers['host'] = '127.0.0.1:8000'
    peers = Peers()
    app.state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, 'per_sender_session')
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='none' WHERE endpoint_id=?",
                               (binding['endpoint_id'],))
    response = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
        actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=['execute_work'],
        max_executions=2, expires_at=iso_plus(deps.clock.now_iso(), 600)))
    assert response.status_code == 200, response.text
    grant = response.json()['data']['grant_id']
    turns, origins = [], []
    for index in range(2):
        def call(actor, name, **args):
            return tool(client, headers[actor]['Authorization'].removeprefix('Bearer '), name, args)
        source = call('operator', 'session_open', agent_id='operator', workspace_id=binding['workspace_id'])
        assert source['ok'], source
        source = source['data']
        created = call('operator', 'handoff_create', workspace_id=binding['workspace_id'], from_agent_id='operator',
            target={'strategy': 'broadcast'}, visibility='eligible', payload='Execute with original creator context',
            session_id=source['session_id'], session_secret=source['session_secret'])
        assert created['ok'], created
        hid = created['data']['handoff_id']
        if origin_write_fails:
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("CREATE TRIGGER fail_execution_origin BEFORE INSERT ON execution_message_origins "
                                       "BEGIN SELECT RAISE(ABORT,'injected origin transfer failure'); END")
        claimed = call('subject', 'handoff_claim', workspace_id=binding['workspace_id'], agent_id='subject',
            handoff_id=hid, runtime_endpoint_id=binding['endpoint_id'], execution_grant_id=grant,
            idempotency_key=f'origin-work-{index}')
        if origin_write_fails:
            assert not claimed['ok']
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('OPEN', 0)
                assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (grant,)).fetchone()[0] == 0
                assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_bindings').fetchone()[0] == 0
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
            assert not peers.sessions
            return
        assert claimed['ok'], claimed
        operation = claimed['data']['runtime_operation']['operation_id']
        expected = json.dumps(['mcp', source['session_id']], separators=(',', ':'))
        with deps.connection_factory.unit_of_work(write=False) as uow:
            message = uow.connection.execute('SELECT message_id FROM delivery_outbox WHERE operation_id=?', (operation,)).fetchone()[0]
            assert uow.connection.execute('SELECT source_session_key FROM execution_message_origins WHERE message_id=?',
                                           (message,)).fetchone()[0] == expected
            turn = dict(uow.connection.execute("SELECT p.operation_id,p.session_id FROM execution_operations p "
                "JOIN execution_domain_deliveries d USING(server_id,executor_id,operation_id) "
                "WHERE d.domain_operation_id=? AND p.action='turn.submit'", (operation,)).fetchone())
            affinity = uow.connection.execute('SELECT sender_agent_id,source_session_key FROM execution_sender_sessions '
                                              'WHERE session_id=?', (turn['session_id'],)).fetchone()
            assert affinity[:] == ('operator', expected)
        wait_receipt(setup, turn)
        turns.append(turn)
        origins.append(expected)
    assert origins[0] != origins[1] and turns[0]['session_id'] != turns[1]['session_id']
    assert len(peers.sessions) == 2
    for index, turn in enumerate(turns):
        assert len(peers.sessions[turn['session_id']].sent) == 1
        wait_receipt(setup, admit(setup, binding, f'close-origin-work-{index}', 'runtime.close',
                                 session_id=turn['session_id']), stages=('SUCCEEDED',))
