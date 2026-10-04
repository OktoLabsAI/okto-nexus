"""Canonical output enters the existing governed result publication paths."""
import json
from pathlib import Path
import time

import pytest
from nexus_connector_core import RuntimeEvent
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_handoff import prepare
from test_message_workspace import call as send_message


def emit(setup, native, turn, text, *, wait_for_terminal=True):
    deps, _, client, *_ = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
        stream['session_id'], stream['stream_epoch'], 0, 'turn_state', 'fixture.result',
        dict(delivery_phase='terminal', delivery_outcome='success', output_text=text), operation_id=turn['operation_id']))
    if wait_for_terminal:
        wait_receipt(setup, turn, stages=('SUCCEEDED',))


def wait_result(setup, state):
    deadline = time.monotonic() + 10
    row = None
    while time.monotonic() < deadline:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            found = uow.connection.execute('SELECT * FROM runtime_results WHERE canonical_operation_id IS NOT NULL').fetchone()
            row = dict(found) if found else None
        if row and row['publication_state'] == state:
            return row
        time.sleep(.02)
    pytest.fail(str(row))


def current_turn(setup):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())


def workspace(setup):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return uow.connection.execute('SELECT workspace_id FROM workspaces').fetchone()[0]


@pytest.mark.parametrize('policy', ['allow', 'deny', 'approval'])
def test_canonical_conversation_result_uses_current_message_policy(connected_local, monkeypatch, policy):
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='conversation' WHERE endpoint_id=?", (binding['endpoint_id'],))
    if policy == 'approval':
        monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
        from test_hitl import _attach, _rule
        deps.config.feature_hitl = True
        _attach(deps, 'subject', governance=[_rule('message_create', 'require_approval')])
    sent = send_message(setup, monkeypatch, workspace_id=workspace(setup))
    assert sent['ok'], sent
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    from okto_nexus.adapters.inbound.mcp.tools.inbox import build_service as inbox_service
    inbox = inbox_service(deps)
    assert inbox.consume_canonical_runtime_results() == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        received = uow.connection.execute('SELECT status,delivered_at,read_at FROM message_deliveries WHERE message_id=? AND recipient_agent_id=?',
            (sent['data']['message_id'], 'subject')).fetchone()
        assert received['status'] == 'delivered'
        assert received['delivered_at'] is not None and received['read_at'] is None
        received_at = received['delivered_at']
    if policy == 'deny':
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE agents SET permissions=? WHERE agent_id=?', (json.dumps(dict(messages=dict(send_direct=False))), 'subject'))
    emit(setup, native, turn, 'A private canonical answer.')
    row = wait_result(setup, {'allow': 'PUBLISHED', 'deny': 'BLOCKED', 'approval': 'PENDING_APPROVAL'}[policy])
    assert row['event_id'] is None and row['runtime_session_id'] is None
    assert row['canonical_operation_id'] == turn['operation_id']
    inbox.consume_canonical_runtime_results()
    assert inbox.consume_canonical_runtime_results() == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM message_deliveries WHERE message_id=? AND recipient_agent_id=?',
            (sent['data']['message_id'], 'subject')).fetchone()[0] == 'read'
        assert uow.connection.execute('SELECT delivered_at FROM message_deliveries WHERE message_id=? AND recipient_agent_id=?',
            (sent['data']['message_id'], 'subject')).fetchone()[0] == received_at
        receipts = [json.loads(r[0]) for r in uow.connection.execute(
            "SELECT body FROM messages WHERE subject LIKE 'runtime processing receipt:%'")]
        assert len(receipts) == 1
        assert receipts[0]['message_ids'] == [sent['data']['message_id']]
        assert receipts[0]['canonical_operation_id'] == turn['operation_id']
        assert receipts[0]['human_read'] is False
    if policy == 'approval':
        response = client.post('/api/v1/approvals/' + row['publication_approval_id'] + '/decision',
            headers=headers['operator'], json=dict(decision='approve'))
        assert response.status_code == 200, response.text
        row = wait_result(setup, 'PUBLISHED')
    if policy != 'deny':
        from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
        service = build_service(deps)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            bound = service._runtime_results.row(uow, row['result_id'])
            message = uow.connection.execute('SELECT * FROM messages WHERE message_id=?', (row['publication_message_id'],)).fetchone()
            assert message['body'] == 'A private canonical answer.' and message['from_agent_id'] == 'subject'
            assert message['parent_message_id'] == sent['data']['message_id']
            assert uow.connection.execute('SELECT recipient_agent_id FROM message_deliveries WHERE message_id=?', (message['message_id'],)).fetchone()[0] == 'operator'
            assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
        repeated = service.create_message(**service._runtime_results.arguments(bound), _runtime_result_id=row['result_id'])
        assert repeated['message_id'] == row['publication_message_id']
    else:
        assert row['output_text'] == 'A private canonical answer.' and row['publication_message_id'] is None
    if policy == 'deny':
        # The permission revision also fences the old execution binding.
        # Drain the owner instead of admitting cleanup under stale authority.
        client.portal.call(setup[1].state.embedded_dispatch_owner.close)
    else:
        wait_receipt(setup, admit(setup, binding, 'publication-close', 'runtime.close', session_id=turn['session_id']), stages=('SUCCEEDED',))


@pytest.mark.parametrize('decision_kind', ['valid', 'wrong_epoch', 'unapproved_contract'])
def test_explicit_canonical_structured_result_completes_governed_handoff(connected_local, monkeypatch, decision_kind):
    setup, binding, native = connected_local
    hid, _, claim, _ = prepare(setup, binding, monkeypatch, workspace_id=workspace(setup))
    claimed = claim(completion_mode='authenticated_nexus_call' if decision_kind == 'unapproved_contract' else 'structured_result_v1')
    assert claimed['ok'], claimed
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    decision = dict(nexus_work_result=dict(schema_version=1, operation_id=claimed['data']['runtime_operation']['operation_id'],
        handoff_id=hid, claim_epoch=2 if decision_kind == 'wrong_epoch' else 1, action='complete', result='Governed output'))
    emit(setup, native, turn, json.dumps(decision))
    row = wait_result(setup, 'WORK_APPLIED' if decision_kind == 'valid' else 'BLOCKED')
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,result FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == (
            ('COMPLETED', 'Governed output') if decision_kind == 'valid' else ('CLAIMED', None))
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_work_outcomes WHERE result_id=?', (row['result_id'],)).fetchone()[0] == (0 if decision_kind == 'unapproved_contract' else 1)
        assert uow.connection.execute("SELECT COUNT(*) FROM messages WHERE subject='Runtime result'").fetchone()[0] == 0
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    wait_receipt(setup, admit(setup, binding, 'structured-close', 'runtime.close', session_id=turn['session_id']), stages=('SUCCEEDED',))
