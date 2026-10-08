"""Session closure preserves siblings and durable, independently scoped facts."""
import asyncio
import json
import threading

import pytest
from nexus_connector_core import RuntimeEvent
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_grant_regressions import mcp_helpers
from test_canonical_native_protocol_regressions import install_native, events
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_agent_recovery_isolation import eventually


def opened(setup, binding, key):
    view = admit(setup, binding, key, 'runtime.start', new_session=True)
    wait_receipt(setup, view)
    return view['scope']['session_id']


def replay(setup, resolution):
    request = {k: resolution[k] for k in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')}
    response = setup[2].post('/v1/runtime/operations', headers=setup[3]['subject'], json=request)
    assert response.status_code == 200, response.text
    return response.json()


def terminal_events(setup, operation_id):
    return [e for e in events(setup) if e.get('operation_id') == operation_id
            and e['payload'].get('delivery_phase') == 'terminal']


def test_closing_owned_codex_process_preserves_sibling_session(connected_local):
    setup, binding, _ = connected_local
    peers, log = install_native(connected_local, _FAKE_SERVER_SOURCE)
    first = opened(setup, binding, 'first-close-scope')
    second = opened(setup, binding, 'second-close-scope')
    processes = [peer._transport._proc for peer in peers]
    assert len(processes) == 2 and processes[0].pid != processes[1].pid
    close = admit(setup, binding, 'close-first-scope', 'runtime.close', session_id=first)
    closed = wait_receipt(setup, close, stages=('SUCCEEDED',))
    assert processes[0].wait(timeout=5) is not None and processes[1].poll() is None
    repeated = replay(setup, close)
    assert repeated['operation_id'] == close['operation_id']
    assert wait_receipt(setup, repeated, stages=('SUCCEEDED',)) == closed
    sent = admit(setup, binding, 'sibling-still-usable', 'turn.submit', session_id=second, text='Sibling response')
    wait_receipt(setup, sent, stages=('SUCCEEDED',))
    eventually(lambda: terminal_events(setup, sent['operation_id']))
    terminals = terminal_events(setup, sent['operation_id'])
    assert len(terminals) == 1 and terminals[0]['session_id'] == second
    assert not [e for e in events(setup) if e['session_id'] == first and e.get('operation_id') == sent['operation_id']]
    wait_receipt(setup, admit(setup, binding, 'close-sibling', 'runtime.close', session_id=second), stages=('SUCCEEDED',))
    assert processes[1].wait(timeout=5) is not None
    wire = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert sum(e.get('method') == 'turn/start' for e in wire) == 1


def test_native_lifecycle_payload_cannot_close_authorized_session(connected_local):
    setup, binding, native = connected_local
    sid = opened(setup, binding, 'untrusted-lifecycle-open')
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    event = RuntimeEvent(stream['server_id'], stream['executor_id'], sid, stream['stream_epoch'],
        0, 'tool_activity', 'nexus/runtime_state',
        dict(origin='nexus', lifecycle_state='stopped', stop_observed=True))
    setup[2].portal.call(native.native.queue.put, event)
    eventually(lambda: any(e.get('native_type') == 'nexus/runtime_state' for e in events(setup)))
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?', (sid,)).fetchone()[0] == 'READY'
    assert not native.native.stopped
    sent = admit(setup, binding, 'after-forged-close', 'turn.submit', session_id=sid, text='Still authorized')
    wait_receipt(setup, sent)
    assert native.native.sent == [('send_turn', sent['operation_id'])]
    wait_receipt(setup, admit(setup, binding, 'actual-close', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))


@pytest.mark.parametrize('projection_failure', [False, True])
def test_repeated_close_preserves_one_native_effect_and_final_event(connected_local, monkeypatch, projection_failure):
    from okto_nexus.bootstrap import embedded_events
    setup, binding, native = connected_local
    sid = opened(setup, binding, 'closing-stream-open')
    turn = admit(setup, binding, 'closing-stream-turn', 'turn.submit', session_id=sid, text='Final work')
    wait_receipt(setup, turn)
    entered, release, captured, project = (threading.Event() for _ in range(4))
    original_close = native.native.close
    calls = []
    async def held_close():
        calls.append('close')
        entered.set()
        while not release.is_set():
            await asyncio.sleep(.01)
        return await original_close()
    monkeypatch.setattr(native.native, 'close', held_close)
    original_project = embedded_events.commit_execution_events
    def deferred(*args, **kwargs):
        if projection_failure and not project.is_set():
            captured.set()
            raise OSError('Fixture projection unavailable while closing')
        return original_project(*args, **kwargs)
    monkeypatch.setattr(embedded_events, 'commit_execution_events', deferred)
    try:
        close = admit(setup, binding, 'close-with-final-event', 'runtime.close', session_id=sid)
        assert entered.wait(10)
        repeated = replay(setup, close)
        assert repeated['operation_id'] == close['operation_id']
        from test_canonical_result_publication import emit
        emit(setup, native, turn, 'Final while closing', wait_for_terminal=False)
        if projection_failure:
            assert captured.wait(10)
        else:
            eventually(lambda: any(e.get('operation_id') == turn['operation_id'] for e in events(setup)))
    finally:
        release.set()
        project.set()
    wait_receipt(setup, close, stages=('SUCCEEDED',))
    wait_receipt(setup, turn, stages=('SUCCEEDED',))
    eventually(lambda: terminal_events(setup, turn['operation_id']))
    terminals = terminal_events(setup, turn['operation_id'])
    assert len(terminals) == 1 and terminals[0]['payload']['output_text'] == 'Final while closing'
    assert calls == ['close']
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?', (sid,)).fetchone()[0] == 'CLOSED'
        assert uow.connection.execute("SELECT count(*) FROM execution_operations WHERE action='runtime.close'").fetchone()[0] == 1
    repeated = replay(setup, close)
    wait_receipt(setup, repeated, stages=('SUCCEEDED',))
    assert calls == ['close']

@pytest.mark.parametrize('terminal_current', [True, False])
def test_active_close_contains_owned_process_without_stalling_sibling(connected_local, terminal_current):
    source = _FAKE_SERVER_SOURCE if terminal_current else _FAKE_SERVER_SOURCE.replace(
        '"id": params["turnId"], "status": "interrupted"',
        '"id": "stale-turn", "status": "interrupted"')
    setup, binding, _ = connected_local
    peers, log = install_native(connected_local, source)
    first = opened(setup, binding, 'active-close-first')
    second = opened(setup, binding, 'active-close-sibling')
    processes = [peer._transport._proc for peer in peers]
    turn = admit(setup, binding, 'active-close-held-turn', 'turn.submit', session_id=first, text='TRIGGER_HOLD')
    wait_receipt(setup, turn)
    state = next(iter(peers[0]._sessions_by_id.values()))
    eventually(lambda: bool(state.active_turn_id))
    active_turn_id = state.active_turn_id
    close = admit(setup, binding, 'active-close-operation', 'runtime.close', session_id=first)
    # This sibling must complete while the original session drains its held turn.
    sibling = admit(setup, binding, 'during-close-sibling', 'turn.submit', session_id=second, text='Sibling remains responsive')
    wait_receipt(setup, sibling, stages=('SUCCEEDED',))
    assert processes[0].poll() is None and processes[1].poll() is None
    def close_finished():
        view = setup[2].get('/v1/runtime/operations/' + close['operation_id'], headers=setup[3]['subject']).json()
        assert setup[1].state.embedded_dispatch_owner.failure is None
        return view.get('executor_stage') == 'SUCCEEDED'
    # Real public close policy allows 30 seconds to drain, then 15 to interrupt.
    eventually(close_finished, seconds=60)
    assert processes[0].wait(timeout=5) is not None and processes[1].poll() is None
    observed = terminal_events(setup, turn['operation_id'])
    if terminal_current:
        wait_receipt(setup, turn, stages=('CANCELLED',))
        eventually(lambda: terminal_events(setup, turn['operation_id']))
        observed = terminal_events(setup, turn['operation_id'])
        assert len(observed) == 1 and observed[0]['payload']['delivery_outcome'] == 'interrupted'
    else:
        assert not observed
        view = setup[2].get('/v1/runtime/operations/' + turn['operation_id'], headers=setup[3]['subject']).json()
        assert view['executor_stage'] != 'SUCCEEDED' and view['possible_effect'] is True
    wire = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert sum(e.get('method') == 'turn/start' for e in wire) == 2
    interrupts = [e for e in wire if e.get('method') == 'turn/interrupt']
    # Forced process cleanup can issue one last containment interrupt after
    # the graceful interrupt timed out. Neither is a new productive turn.
    assert len(interrupts) == 1 if terminal_current else 1 <= len(interrupts) <= 2
    assert all(e['params']['turnId'] == active_turn_id for e in interrupts)
    repeated = replay(setup, close)
    assert repeated['operation_id'] == close['operation_id']
    assert [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()] == wire
    wait_receipt(setup, admit(setup, binding, 'active-close-final-sibling', 'runtime.close', session_id=second), stages=('SUCCEEDED',))


def test_distinct_approved_profiles_have_separate_owned_native_processes(connected_local, monkeypatch):
    from test_canonical_identity_lifecycle import second_binding
    from test_canonical_profile_requirements import configure, profile
    setup, first, _ = connected_local
    second = second_binding(setup, monkeypatch, adapter_id='codex_app_server')
    configure(setup, second, {'disabled_capabilities': ['managed_work', 'approvals']})
    assert profile(setup, first)['profile_id'] != profile(setup, second)['profile_id']
    peers, log = install_native(connected_local, _FAKE_SERVER_SOURCE)
    sessions = [opened(setup, binding, f'profile-isolation-{index}') for index, binding in enumerate((first, second))]
    assert peers[0]._transport._proc.pid != peers[1]._transport._proc.pid
    for index, binding in enumerate((first, second)):
        sent = admit(setup, binding, f'profile-isolated-turn-{index}', 'turn.submit', session_id=sessions[index], text=f'Profile {index}')
        wait_receipt(setup, sent, stages=('SUCCEEDED',))
        eventually(lambda: terminal_events(setup, sent['operation_id']))
        assert all(event['session_id'] == sessions[index] for event in terminal_events(setup, sent['operation_id']))
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        for index, binding in enumerate((first, second)):
            row = uow.connection.execute('SELECT s.binding_id,b.endpoint_id FROM execution_sessions s '
                'JOIN execution_bindings b USING(server_id,executor_id,binding_id) WHERE s.session_id=?', (sessions[index],)).fetchone()
            assert tuple(row) == (binding['binding_id'], binding['endpoint_id'])
    for index, binding in enumerate((first, second)):
        wait_receipt(setup, admit(setup, binding, f'profile-isolated-close-{index}', 'runtime.close', session_id=sessions[index]), stages=('SUCCEEDED',))
        assert peers[index]._transport._proc.wait(timeout=5) is not None
