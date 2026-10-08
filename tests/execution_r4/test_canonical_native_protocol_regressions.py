"""Core native pipe failures and stale controls retain scoped durable evidence."""
import asyncio
import json
import sys
import time

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_grant_regressions import mcp_helpers
from test_agent_recovery_isolation import eventually
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_canonical_delivery import connected_local as work_connected


def install_native(connected, source, *, environment=None):
    from nexus_connector_core.native.adapters.codex import CodexAppServerConnector
    from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
    from nexus_connector_core.native.redaction import NativeSecretRedactor, credential_values
    setup, binding, _ = connected
    _, app, _, _, *_, root = setup
    peers = []
    log = root / "native-wire.jsonl"
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            peer = CodexAppServerConnector(command=[sys._base_executable, "-u", "-c", source, str(log)],
                cwd=str(root), env=environment or {})
            peers.append(peer)
            native = await asyncio.to_thread(peer.start, owning_agent_id=context.agent_id)
            return CopiedAdapterSession(peer, native, session_id=session_id, stream_epoch=stream_epoch, context=context,
                redactor=NativeSecretRedactor(credential_values(environment or {})))
    app.state.embedded_dispatch_owner.native_factory = Factory()
    return peers, log


def open_native(connected, source, *, environment=None):
    setup, binding, _ = connected
    peers, log = install_native(connected, source, environment=environment)
    opened = admit(setup, binding, "protocol-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    return setup, binding, opened["scope"]["session_id"], peers[0], log


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_managed_interrupt_ack_waits_for_native_terminal(work_connected, monkeypatch, surface):
    from test_canonical_handoff import prepare
    from test_pr34_remediation import tool
    setup, binding, _ = work_connected
    deps, _, client, headers, *_, root = setup
    release, ack = root / 'release-work-interrupt', root / 'work-interrupt-ack'
    marker = '            write_msg(\n                {\n                    "method": "turn/completed",'
    assert _FAKE_SERVER_SOURCE.count(marker) == 1
    gate = (f'            open({str(ack)!r}, "w").close()\n'
            '            deadline = time.monotonic() + 20\n'
            f'            while not os.path.exists({str(release)!r}):\n'
            '                assert time.monotonic() < deadline\n'
            '                time.sleep(.01)\n')
    peers, log = install_native(work_connected, _FAKE_SERVER_SOURCE.replace(marker, gate + marker))
    handoff, _, claim, _ = prepare(setup, binding, monkeypatch, payload='TRIGGER_HOLD managed work')
    claimed = claim()
    assert claimed['ok'], claimed
    with deps.connection_factory.unit_of_work(write=False) as uow:
        turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
    wait_receipt(setup, turn)
    assert len(peers) == 1
    peer = peers[0]
    state = next(iter(peer._sessions_by_id.values()))
    eventually(lambda: bool(state.active_turn_id))
    sid = turn['session_id']
    body = dict(idempotency_key='managed-interrupt', expected_turn_id=state.active_turn_id)
    try:
        if surface == 'rest':
            response = client.post(f'/api/v1/harness/sessions/{sid}/interrupt', headers=headers['operator'], json=body).json()
        else:
            response = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '),
                'harness_interrupt', dict(session_id=sid, **body))
        assert response['ok'], response
        eventually(ack.exists)
        control = wait_receipt(setup, response['data'])
        # An acknowledged control is independent of the original work terminal.
        assert control['executor_stage'] in ('SUBMITTED', 'SUCCEEDED')
        view = client.get(f"/v1/runtime/operations/{turn['operation_id']}", headers=headers['subject']).json()
        assert view['executor_stage'] == 'SUBMITTED', view
        assert not [e for e in events(setup) if e.get('operation_id') == turn['operation_id']
                    and e['payload'].get('delivery_phase') == 'terminal']
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT status,result FROM handoffs WHERE handoff_id=?', (handoff,)).fetchone()[:] == ('CLAIMED', None)
            assert uow.connection.execute('SELECT canonical_terminal_operation_id FROM delivery_outbox').fetchone()[0] is None
    finally:
        release.touch()
    wait_receipt(setup, turn, stages=('CANCELLED',))
    def captured_terminals():
        return [e for e in events(setup) if e.get('operation_id') == turn['operation_id']
                and e['payload'].get('delivery_phase') == 'terminal']
    eventually(captured_terminals)
    terminals = captured_terminals()
    assert len(terminals) == 1 and terminals[0]['payload']['delivery_outcome'] == 'interrupted'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,result FROM handoffs WHERE handoff_id=?', (handoff,)).fetchone()[:] == ('CLAIMED', None)
        assert uow.connection.execute('SELECT count(*) FROM delivery_outbox').fetchone()[0] == 1
    wire = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert sum(m.get('method') == 'turn/interrupt' for m in wire) == 1
    wait_receipt(setup, admit(setup, binding, 'managed-interrupt-close', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))


def events(setup):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return [json.loads(r[0]) for r in uow.connection.execute("SELECT payload_json FROM execution_event_ingress")]


@pytest.mark.parametrize("fault", ["oversized", "unknown_threads"])
def test_native_protocol_fault_is_durable_and_reaps_peer_without_success(connected_local, fault):
    injection = ('        sys.stdout.write("x" * 2000000)\n        sys.stdout.flush()\n        time.sleep(60)\n'
        if fault == "oversized" else
        '        for i in range(512):\n            write_msg({"method":"item/agentMessage/delta", '
        '"params":{"threadId":"unknown-"+str(i), "delta":"fixture"}})\n        return\n')
    source = _FAKE_SERVER_SOURCE.replace('    if "TRIGGER_HOLD" in text:',
        '    if "TRIGGER_FAULT" in text:\n' + injection + '    if "TRIGGER_HOLD" in text:')
    assert source != _FAKE_SERVER_SOURCE
    setup, binding, sid, peer, _ = open_native(connected_local, source)
    sent = admit(setup, binding, "protocol-fault", "turn.submit", session_id=sid, text="TRIGGER_FAULT")
    marker = "frame_limit_exceeded" if fault == "oversized" else "early_event_limit_exceeded"
    eventually(lambda: marker in json.dumps(events(setup)))
    assert peer._transport._proc.wait(timeout=5) != 0
    observed = events(setup)
    faults = [e for e in observed if marker in json.dumps(e)]
    assert faults and all(e["sequence"] > 0 for e in faults)
    assert all(len(json.dumps(e)) < 5000 for e in faults)
    assert not [e for e in observed if e["payload"].get("delivery_outcome") == "success"]
    view = setup[2].get(f"/v1/runtime/operations/{sent['operation_id']}", headers=setup[3]["subject"])
    assert view.status_code == 200 and view.json().get("executor_stage") != "SUCCEEDED", view.text


def test_slow_native_capture_overflow_is_contained_with_durable_uncertainty(connected_local, monkeypatch):
    import threading
    from nexus_connector_core.native import runtime_bridge
    entered, release = threading.Event(), threading.Event()
    original = runtime_bridge._next_event
    def delayed_read(iterator):
        event = original(iterator)
        if event is not None and event.kind == 'output_delta' and not entered.is_set():
            entered.set()
            assert release.wait(15)
        return event
    monkeypatch.setattr(runtime_bridge, '_next_event', delayed_read)
    source = _FAKE_SERVER_SOURCE.replace('    if "TRIGGER_HOLD" in text:',
        '    if "TRIGGER_FLOOD" in text:\n'
        '        for i in range(400):\n'
        '            write_msg({"method":"item/agentMessage/delta","params":{'
        '"threadId":thread_id,"turnId":turn_id,"delta":str(i)+"x"*8192}})\n'
        '        return\n'
        '    if "TRIGGER_HOLD" in text:')
    setup, binding, sid, peer, _ = open_native(connected_local, source)
    eventually(lambda: bool(peer._subscribers))
    queues = list(peer._subscribers)
    try:
        sent = admit(setup, binding, 'slow-capture-flood', 'turn.submit', session_id=sid, text='TRIGGER_FLOOD')
        assert entered.wait(5)
        # The Core stream owns one bounded subscription. Once its queue is
        # full, the adapter detaches it; the retained prefix then ends in a gap.
        eventually(lambda: not peer._subscribers)
        assert all(queue.qsize() <= 128 for queue in queues)
    finally:
        release.set()
    # Allow the normal five-second graceful/force containment phases plus
    # publication and recovery scheduling; do not manually close the peer.
    eventually(lambda: peer._transport._proc.poll() is not None, seconds=25)
    eventually(lambda: 'EVENT_STREAM_UNAVAILABLE' in json.dumps(events(setup)))
    observed = events(setup)
    assert observed
    assert not [e for e in observed if e['payload'].get('delivery_outcome') == 'success']
    view = setup[2].get(f"/v1/runtime/operations/{sent['operation_id']}", headers=setup[3]['subject'])
    assert view.status_code == 200, view.text
    assert view.json()['executor_stage'] != 'SUCCEEDED', view.text
    faults = [e for e in observed if e['payload'].get('code') == 'EVENT_STREAM_UNAVAILABLE']
    assert faults and all(e['sequence'] > 0 for e in faults)


def test_stale_native_target_is_rejected_and_matching_interrupt_completes_original_turn(connected_local):
    setup, binding, sid, peer, log = open_native(connected_local, _FAKE_SERVER_SOURCE)
    sent = admit(setup, binding, "held-turn", "turn.submit", session_id=sid, text="TRIGGER_HOLD")
    wait_receipt(setup, sent)
    state = next(iter(peer._sessions_by_id.values()))
    eventually(lambda: bool(state.active_turn_id))
    target = state.active_turn_id
    stale = admit(setup, binding, "stale-native-target", "turn.steer", session_id=sid, text="Must not reach native pipe",
        target=dict(kind="native_turn_id", expected_turn_id="stale-turn"))
    refused = wait_receipt(setup, stale, stages=("FAILED",))
    assert refused["possible_effect"] is False
    wire = [json.loads(line) for line in log.read_text().splitlines()]
    assert not [m for m in wire if m.get("method") == "turn/steer"]
    interrupted = admit(setup, binding, "matching-interrupt", "turn.interrupt", session_id=sid,
        target=dict(kind="native_turn_id", expected_turn_id=target))
    wait_receipt(setup, interrupted)
    wait_receipt(setup, sent, stages=("CANCELLED",))
    wait_receipt(setup, admit(setup, binding, "protocol-close", "runtime.close", session_id=sid), stages=("SUCCEEDED",))
    assert peer._transport._proc.wait(timeout=5) is not None


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_queued_control_for_finished_turn_cannot_reach_next_turn(connected_local, surface):
    from test_pr34_remediation import tool
    release = connected_local[0][-1] / 'release-first-turn'
    source = _FAKE_SERVER_SOURCE.replace('    if "TRIGGER_HOLD" in text:',
        '    if "FINISH_AT_BARRIER" in text:\n'
        '        deadline = time.monotonic() + 20\n'
        f'        while not os.path.exists({str(release)!r}):\n'
        '            assert time.monotonic() < deadline\n'
        '            time.sleep(.01)\n'
        '    if "TRIGGER_HOLD" in text:')
    setup, binding, sid, peer, log = open_native(connected_local, source)
    setup[2].headers['host'] = '127.0.0.1:8000'
    first = admit(setup, binding, 'queued-control-first', 'turn.submit', session_id=sid, text='FINISH_AT_BARRIER')
    wait_receipt(setup, first)
    state = next(iter(peer._sessions_by_id.values()))
    eventually(lambda: bool(state.active_turn_id))
    target = state.active_turn_id
    lock = setup[1].state.embedded_dispatch_owner.pump.send_lock
    setup[2].portal.call(lock.acquire)
    try:
        body = dict(idempotency_key='queued-stale-control', payload=dict(text='Must not reach the next turn'),
                    expected_turn_id=target)
        if surface == 'rest':
            response = setup[2].post(f'/api/v1/harness/sessions/{sid}/steer', headers=setup[3]['subject'], json=body).json()
        else:
            response = tool(setup[2], setup[3]['subject']['Authorization'].removeprefix('Bearer '),
                            'harness_steer', dict(session_id=sid, **body))
        assert response['ok'], response
        control = response['data']
        release.touch()
        wait_receipt(setup, first, stages=('SUCCEEDED',))
        second = admit(setup, binding, 'queued-control-second', 'turn.submit', session_id=sid, text='Healthy next turn')
    finally:
        release.touch()
        setup[2].portal.call(lock.release)
    refused = wait_receipt(setup, control, stages=('FAILED',))
    assert refused['possible_effect'] is False
    wait_receipt(setup, second, stages=('SUCCEEDED',))
    wire = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert not [m for m in wire if m.get('method') == 'turn/steer']
    assert len([m for m in wire if m.get('method') == 'turn/start']) == 2
    wait_receipt(setup, admit(setup, binding, 'queued-control-close', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))


@pytest.mark.parametrize('adapter,bad_reply', [
    ('pi_rpc', {'success': False, 'error': 'fixture command unsupported'}),
    ('pi_rpc', {'success': 'true', 'data': {}}),
    ('pi_rpc', {'success': True, 'data': []}),
    ('codex_app_server', ''), ('codex_app_server', 42), ('codex_app_server', None),
])
def test_invalid_native_readiness_is_contained_and_other_binding_remains_usable(connected_local, monkeypatch, adapter, bad_reply):
    from nexus_connector_core.native import runtime_bridge
    from nexus_connector_core.native.adapters.codex import CodexAppServerConnector
    from nexus_connector_core.native.adapters.pi import PiRpcConnector
    from test_canonical_identity_lifecycle import second_binding
    from test_vertical_inventory import _Native

    setup, codex_binding, _ = connected_local
    pi_binding = second_binding(setup, monkeypatch)
    deps, app, client, _, *_, root = setup
    failed_binding, healthy_binding = ((pi_binding, codex_binding) if adapter == 'pi_rpc'
                                       else (codex_binding, pi_binding))
    wire = root / 'readiness-wire.jsonl'
    if adapter == 'pi_rpc':
        source = ('import sys,json\nfor line in sys.stdin:\n'
            ' msg=json.loads(line)\n'
            ' with open(sys.argv[1],"a") as log: log.write(json.dumps(msg)+"\\n")\n'
            f' print(json.dumps(dict(type="response",command=msg["type"],**{bad_reply!r})),flush=True)\n')
        connector = PiRpcConnector
    else:
        source = _FAKE_SERVER_SOURCE.replace('thread_id = next_thread_id()', f'thread_id = {bad_reply!r}')
        source = source.replace('method = msg.get("method")', 'method = msg.get("method"); log({"method": method})')
        connector = CodexAppServerConnector
    peers = []
    def construct(**options):
        peer = connector(command=[sys._base_executable, '-u', '-c', source, str(wire)], cwd=str(root), env={})
        peers.append(peer)
        return peer
    # Qualify only the synthetic executable. The installed Core factory still
    # performs the real handshake, rejection normalization and process cleanup.
    monkeypatch.setattr(runtime_bridge, 'qualified_build', lambda *a, **k: True)
    monkeypatch.setattr(runtime_bridge, 'load_adapter', lambda _: construct)
    async def environment(prepared):
        return {}
    bridge = runtime_bridge.CopiedAdapterFactory(environment)
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            if prepared.intent.adapter_id == adapter:
                return await bridge.open(prepared, session_id, context, stream_epoch=stream_epoch)
            return _Native()
    app.state.embedded_dispatch_owner.native_factory = Factory()
    try:
        opened = admit(setup, failed_binding, 'invalid-native-readiness', 'runtime.start', new_session=True)
        refused = wait_receipt(setup, opened, stages=('FAILED',))
        # Native startup did occur; terminal failure and confirmed containment
        # must not be misreported as a pre-spawn refusal.
        assert refused['possible_effect'] is True, refused
        assert 'NATIVE_PROTOCOL_INCOMPATIBLE' in json.dumps(refused), refused
        assert len(peers) == 1
        transport = peers[0]._transport
        assert transport is None or transport._proc.poll() is not None
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert not uow.connection.execute("SELECT 1 FROM execution_sessions WHERE binding_id=? AND lifecycle_state='READY'",
                (failed_binding['binding_id'],)).fetchone()
        messages = [json.loads(line) for line in wire.read_text().splitlines()]
        assert not [m for m in messages if m.get('method') == 'turn/start' or m.get('type') == 'prompt']
        healthy = admit(setup, healthy_binding, 'healthy-after-incompatible', 'runtime.start', new_session=True)
        wait_receipt(setup, healthy)
        wait_receipt(setup, admit(setup, healthy_binding, 'healthy-after-incompatible-close', 'runtime.close',
            session_id=healthy['session_id']), stages=('SUCCEEDED',))
        assert app.state.embedded_dispatch_owner.failure is None
    finally:
        bridge.close()
