"""Disposable real-native owner, cut at an exact durable result boundary."""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
tests = Path(sys.argv[2])
sys.path[:0] = [str(tests), str(tests / 'execution_r4')]
root, mode, cut = Path(sys.argv[3]), sys.argv[4], sys.argv[5]
record_path = root / 'crash-record.json'

if mode == 'produce':
    import pytest
    from test_embedded_dispatch import qualified_contract, admit, wait_receipt
    from test_local_realization import local_setup
    from test_canonical_delivery import connected_local, enable, send
    from test_canonical_native_protocol_regressions import install_native
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    from nexus_connector_core.journal import SQLiteJournal
    from okto_nexus.bootstrap import embedded_events

    patches = pytest.MonkeyPatch()
    qualified_contract.__wrapped__(patches)
    lifetime = local_setup.__wrapped__(root, patches, None)
    setup = next(lifetime)
    connected = connected_local.__wrapped__(setup)
    _, binding, _ = connected
    enable(setup, binding)
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_policy_defaults SET session_policy='shared'")
    source = _FAKE_SERVER_SOURCE
    if cut == 'after_terminal_capture_burst':
        line = '    write_msg({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": turn_id, "itemId": item_id, "delta": text}})'
        assert source.count(line) == 1
        source = source.replace(line,
            '    for index in range(140):\n'
            '        write_msg({"method":"item/agentMessage/delta", "params": {"threadId":thread_id,"turnId":turn_id,"itemId":item_id,"delta":"Please review this message. " + str(index)}})\n'
            '        if (index + 1) % 10 == 0:\n'
            f'            marker = {str(root / "captured-")!r} + str(index + 1)\n'
            '            deadline = time.monotonic() + 15\n'
            '            while not os.path.exists(marker):\n'
            '                assert time.monotonic() < deadline\n'
            '                time.sleep(.01)')
    peers, wire = install_native(connected, source)
    opened = admit(setup, binding, 'crash-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    deps, app, client, headers, body, candidate, workspace = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        expiry = uow.connection.execute("SELECT lease_expires_at FROM runtime_dispatcher_owner WHERE owner_key='dispatcher'").fetchone()[0]
    record = dict(home=str(deps.config.home_dir), headers=headers, opened=opened,
        binding=binding, owner_expiry=expiry, pid=os.getpid(), native_pid=peers[0]._transport._proc.pid,
        wire=str(wire), workspace=str(workspace), cut=cut)
    record_path.write_text(json.dumps(record), encoding='utf-8')

    def crash(event):
        with deps.connection_factory.unit_of_work(write=False) as uow:
            domain = dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
            turn = dict(uow.connection.execute("SELECT * FROM execution_operations WHERE action='turn.submit'").fetchone())
        marker = dict(operation_id=domain['operation_id'], turn=turn['operation_id'],
            session_id=turn['session_id'], delivery_id=domain['delivery_id'], message_id=domain['message_id'],
            native_type=event.get('native_type'), phase=event.get('payload', {}).get('delivery_phase'))
        (root / 'crash-cut.json').write_text(json.dumps(marker), encoding='utf-8')
        os._exit(78)

    original_record = SQLiteJournal.record_event
    captured = 0
    async def capture(journal, event):
        global captured
        from dataclasses import asdict
        terminal = event.payload.get('delivery_phase') == 'terminal'
        if ((cut == 'before_output_capture' and event.category == 'text_delta')
                or (cut == 'before_terminal_capture' and terminal)):
            crash(asdict(event))
        saved = await original_record(journal, event)
        if event.category == 'text_delta':
            captured += 1
            if captured % 10 == 0:
                (root / f'captured-{captured}').touch()
        if cut.startswith('after_terminal_capture') and terminal:
            crash(asdict(saved))
        return saved
    patches.setattr(SQLiteJournal, 'record_event', capture)
    original_project = embedded_events.commit_execution_events
    def project(*args, **kwargs):
        terminal = next((event for event in kwargs['frame']['events']
            if event.get('payload', {}).get('delivery_phase') == 'terminal'), None)
        if cut.startswith('after_terminal_capture'):
            raise OSError('Hold Server projection before crash')
        result = original_project(*args, **kwargs)
        if cut == 'after_projection_commit' and terminal:
            crash(terminal)
        return result
    patches.setattr(embedded_events, 'commit_execution_events', project)
    deadline = time.monotonic() + 20
    while not (root / 'allow-send').exists():
        assert time.monotonic() < deadline
        time.sleep(.01)
    created = send(setup, patches)
    assert created['ok'], created
    time.sleep(30)
    raise AssertionError('Native process did not reach the requested crash cut')

from okto_nexus.bootstrap import embedded_inventory, runtime_host
embedded_inventory.discover_local_candidates = lambda **_: SimpleNamespace(candidates=())
def forbidden(*args, **kwargs):
    (root / 'unexpected-native-launch').touch()
    raise AssertionError('Recovery cannot replay the native prompt')
runtime_host.create_runtime = forbidden
from okto_nexus.adapters.inbound.cli.serve import run_serve
raise SystemExit(run_serve(sys.argv[6:]))
