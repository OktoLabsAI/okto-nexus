"""Public operation facts distinguish admission, a wire write and completion."""
import asyncio
import json
import threading

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_runtime_contract_migration import mcp
from test_agent_recovery_isolation import eventually
from test_canonical_native_protocol_regressions import open_native
from test_harness_codex_connector import _FAKE_SERVER_SOURCE


def read(setup, operation):
    response = setup[2].get('/v1/runtime/operations/' + operation, headers=setup[3]['subject'])
    assert response.status_code == 200, response.text
    return response.json()


def inspect(setup, monkeypatch, operation):
    client, headers = setup[2:4]
    canonical = client.get('/v1/runtime/operations/' + operation, headers=headers['subject'])
    compatible = client.get('/api/v1/harness/operations/' + operation, headers=headers['subject'])
    tool = mcp(setup, monkeypatch, headers['subject']['Authorization'].removeprefix('Bearer '),
               'harness_get', dict(operation_id=operation))
    assert canonical.status_code == compatible.status_code == 200
    assert tool['ok'], tool
    for view in (compatible.json()['data'], tool['data']):
        for key in ('operation_id', 'executor_stage', 'possible_effect', 'result'):
            assert view[key] == canonical.json()[key]
    return canonical.json()


def test_pending_wire_receipt_and_native_terminal_have_distinct_public_evidence(connected_local, monkeypatch):
    from test_canonical_result_publication import emit
    setup, binding, native = connected_local
    owner = setup[1].state.embedded_dispatch_owner
    opened = admit(setup, binding, 'state-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    entered, release = threading.Event(), asyncio.Event()
    publish = owner._publish
    async def held(binding, receipt):
        if receipt.operation_id != opened['operation_id'] and receipt.stage == 'SUBMITTED':
            entered.set()
            await release.wait()
        return await publish(binding, receipt)
    monkeypatch.setattr(owner, '_publish', held)
    setup[2].portal.call(owner.pump.send_lock.acquire)
    try:
        turn = admit(setup, binding, 'state-turn', 'turn.submit', session_id=opened['session_id'], text='State observation')
        pending = inspect(setup, monkeypatch, turn['operation_id'])
        assert pending['executor_stage'] is None and pending['possible_effect'] is False
        assert pending['result'] is None and native.native.sent == []
    finally:
        setup[2].portal.call(owner.pump.send_lock.release)
    try:
        assert entered.wait(10)
        unconfirmed = inspect(setup, monkeypatch, turn['operation_id'])
        assert unconfirmed['executor_stage'] is None and unconfirmed['possible_effect'] is True
        assert unconfirmed['result'] is None and len(native.native.sent) == 1
    finally:
        setup[2].portal.call(release.set)
    wait_receipt(setup, turn)
    accepted = inspect(setup, monkeypatch, turn['operation_id'])
    assert accepted['executor_stage'] == 'SUBMITTED' and accepted['result'] is None
    emit(setup, native, turn, 'One captured answer')
    eventually(lambda: read(setup, turn['operation_id'])['result'] is not None)
    completed = inspect(setup, monkeypatch, turn['operation_id'])
    assert completed['executor_stage'] == 'SUCCEEDED'
    assert 'One captured answer' in json.dumps(completed['result'])
    assert len(native.native.sent) == 1


def test_native_pushed_events_drive_public_completion_without_status_queries(connected_local, monkeypatch):
    source = _FAKE_SERVER_SOURCE.replace('method = msg.get("method")',
        'method = msg.get("method"); log({"observed_request_method": method})')
    assert source != _FAKE_SERVER_SOURCE
    setup, binding, sid, peer, log = open_native(connected_local, source)
    turn = admit(setup, binding, 'pushed-state-turn', 'turn.submit', session_id=sid, text='TRIGGER_HOLD')
    wait_receipt(setup, turn)
    state = next(iter(peer._sessions_by_id.values()))
    eventually(lambda: bool(state.active_turn_id))
    accepted = inspect(setup, monkeypatch, turn['operation_id'])
    assert accepted['executor_stage'] == 'SUBMITTED'
    interrupt = admit(setup, binding, 'pushed-state-interrupt', 'turn.interrupt', session_id=sid,
                      target=dict(kind='native_turn_id', expected_turn_id=state.active_turn_id))
    wait_receipt(setup, interrupt)
    wait_receipt(setup, turn, stages=('CANCELLED',))
    eventually(lambda: read(setup, turn['operation_id'])['result'] is not None)
    final = inspect(setup, monkeypatch, turn['operation_id'])
    assert final['executor_stage'] == 'CANCELLED'
    events = setup[2].get('/v1/runtime/sessions/' + sid + '/events', headers=setup[3]['subject']).json()['events']
    correlated = [event for event in events if event.get('operation_id') == turn['operation_id']]
    phases = {event['payload'].get('delivery_phase') for event in correlated}
    assert {'started', 'terminal'} <= phases, events
    assert all(event['sequence'] > 0 for event in correlated)
    replay = mcp(setup, monkeypatch, setup[3]['subject']['Authorization'].removeprefix('Bearer '),
                 'harness_event_list', dict(session_id=sid))
    assert replay['ok'] and replay['data']['events'] == events, replay
    wire = [json.loads(line) for line in log.read_text().splitlines()]
    methods = [message['observed_request_method'] for message in wire if message.get('observed_request_method')]
    assert methods[methods.index('turn/start'):] == ['turn/start', 'turn/interrupt'], methods
    wait_receipt(setup, admit(setup, binding, 'pushed-state-close', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))
