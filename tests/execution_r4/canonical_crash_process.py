"""Disposable Server and native protocol peer, cut at a durable boundary."""
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
administrative = cut.startswith('admin_')
queued = cut.startswith('queue_')
cut = cut.removeprefix('admin_').removeprefix('queue_')
record_path = root / 'crash-record.json'


def queue_human_inputs(app, client, opened):
    scope = opened['scope']
    generation = scope['session_owner_generation']
    exact = {key: scope[key] for key in ('server_id', 'executor_id', 'session_id', 'binding_id',
                                       'workspace_id', 'workspace_binding_id', 'agent_id')}
    session = exact['session_id']
    path = f'/api/v1/runtime-management/runtime/sessions/{session}'
    query = {key: value for key, value in exact.items() if key != 'session_id'}
    query['expected_session_generation'] = generation
    base = {'scope': exact, 'expected_session_generation': generation}
    auth = app.state.operator_auth
    assert auth.configure('queue-crash-human', 'fixture-password-long', local=True)
    token = auth.login('queue-crash-human', 'fixture-password-long')
    assert token
    client.cookies.set('nexus_operator_session', token)
    ui = {'x-nexus-ui': '1'}

    def pause(paused):
        response = client.get(path + '/inputs', params=query)
        assert response.status_code == 200, response.text
        page = response.json()
        response = client.post(path + '/inputs/queue-state', headers=ui, json=base | {
            'capability_revision': page['pause_capability_revision'],
            'expected_queue_revision': page['queue_revision'], 'paused': paused,
        })
        assert response.status_code == 200, response.text

    pause(True)
    response = client.get(path + '/interaction', params=query)
    assert response.status_code == 200, response.text
    revision = response.json()['next_turn']['capability_revision']
    inputs = {}
    for intent in ('original-queued-input', 'retained-follower'):
        response = client.post(path + '/inputs', headers=ui, json=base | {
            'capability_revision': revision, 'client_intent_id': intent,
            'content': [{'type': 'text', 'text': intent}],
        })
        assert response.status_code == 202, response.text
        item = response.json()
        assert item['status'] == 'QUEUED' and item['operation_id'] is None
        inputs[intent] = item['input_id']
    return {'path': path, 'query': query, 'exact': exact, 'inputs': inputs, 'token': token}, pause


if mode == 'produce':
    import pytest
    from test_embedded_dispatch import qualified_contract, admit, wait_receipt
    from test_local_realization import local_setup
    from test_canonical_delivery import connected_local, enable, send
    from test_canonical_native_protocol_regressions import install_native
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    from nexus_connector_core.journal import SQLiteJournal
    from okto_nexus.bootstrap import embedded_dispatch, embedded_events

    patches = pytest.MonkeyPatch()
    qualified_contract.__wrapped__(patches)
    if queued:
        from test_session_input_runtime import _prepare_interactive_fixture

        _prepare_interactive_fixture(patches)
    lifetime = local_setup.__wrapped__(root, patches, None)
    setup = next(lifetime)
    connected = connected_local.__wrapped__(setup)
    _, binding, _ = connected
    enable(setup, binding)
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_policy_defaults SET session_policy='shared'")
    source = _FAKE_SERVER_SOURCE
    if cut in ('before_turn_receipt', 'after_turn_receipt'):
        # The real peer acknowledges the prompt and keeps its turn running.
        # No terminal can win the receipt race or fabricate completion.
        assert '    if "TRIGGER_HOLD" in text:' in source
        source = source.replace('    if "TRIGGER_HOLD" in text:', '    if True:')
    if cut == 'after_terminal_capture_burst':
        line = '    write_msg({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": turn_id, "itemId": item_id, "delta": text}})'
        assert source.count(line) == 1
        source = source.replace(line,
            '    for index in range(140):\n'
            '        write_msg({"method":"item/agentMessage/delta", "params": {"threadId":thread_id,"turnId":turn_id,"itemId":item_id,"delta":"Please review this message. " + str(index)}})')
    peers, wire = install_native(connected, source)
    opened = admit(setup, binding, 'crash-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    deps, app, client, headers, body, candidate, workspace = setup
    queue, set_paused = queue_human_inputs(app, client, opened) if queued else (None, None)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        expiry = uow.connection.execute("SELECT lease_expires_at FROM runtime_dispatcher_owner WHERE owner_key='dispatcher'").fetchone()[0]
    record = dict(home=str(deps.config.home_dir), headers=headers, opened=opened,
        binding=binding, owner_expiry=expiry, pid=os.getpid(), native_pid=peers[0]._transport._proc.pid,
        wire=str(wire), workspace=str(workspace), cut=cut, queue=queue)
    pending_record = record_path.with_suffix('.tmp')
    pending_record.write_text(json.dumps(record), encoding='utf-8')
    pending_record.replace(record_path)

    def crash(event):
        with deps.connection_factory.unit_of_work(write=False) as uow:
            found = uow.connection.execute('SELECT * FROM delivery_outbox').fetchone()
            domain = dict(found) if found else None
            turn = dict(uow.connection.execute("SELECT * FROM execution_operations WHERE action='turn.submit'").fetchone())
            if queued:
                inputs = uow.connection.execute('SELECT input_id, status, operation_id FROM session_interaction_inputs '
                                                'ORDER BY enqueue_sequence').fetchall()
                assert [tuple(row) for row in inputs] == [
                    (queue['inputs']['original-queued-input'], 'DISPATCHING', turn['operation_id']),
                    (queue['inputs']['retained-follower'], 'QUEUED', None),
                ]
                assert not uow.connection.execute('SELECT 1 FROM execution_receipts WHERE operation_id=?',
                                                  (turn['operation_id'],)).fetchone()
        marker = dict(operation_id=domain['operation_id'] if domain else turn['operation_id'], turn=turn['operation_id'],
            session_id=turn['session_id'], delivery_id=domain['delivery_id'] if domain else None,
            message_id=domain['message_id'] if domain else None,
            native_type=event.get('native_type'), phase=event.get('payload', {}).get('delivery_phase'))
        (root / 'crash-cut.json').write_text(json.dumps(marker), encoding='utf-8')
        os._exit(78)

    original_record = SQLiteJournal.record_event
    async def capture(journal, event):
        from dataclasses import asdict
        terminal = event.payload.get('delivery_phase') == 'terminal'
        if ((cut == 'before_output_capture' and event.category == 'text_delta')
                or (cut == 'before_terminal_capture' and terminal)):
            crash(asdict(event))
        saved = await original_record(journal, event)
        if cut.startswith('after_terminal_capture') and terminal:
            crash(asdict(saved))
        return saved
    patches.setattr(SQLiteJournal, 'record_event', capture)
    original_receipt = SQLiteJournal.record_receipt
    async def record_receipt(journal, key, receipt):
        selected = (cut in ('before_turn_receipt', 'after_turn_receipt')
            and receipt.stage == 'SUBMITTED' and key.operation_id != opened['operation_id'])
        if selected and cut == 'before_turn_receipt':
            crash(dict(native_type='before_core_submit_receipt', payload={}))
        saved = await original_receipt(journal, key, receipt)
        if selected and cut == 'after_turn_receipt':
            crash(dict(native_type='after_core_submit_receipt', payload={}))
        return saved
    patches.setattr(SQLiteJournal, 'record_receipt', record_receipt)
    if queued and cut == 'after_terminal_capture':
        original_append = embedded_dispatch.append_execution_receipt

        def append(*args, frame, **kwargs):
            if frame['operation_id'] != opened['operation_id']:
                raise OSError('Hold queued-turn receipt publication until the crash')
            return original_append(*args, frame=frame, **kwargs)

        patches.setattr(embedded_dispatch, 'append_execution_receipt', append)
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
    if queued:
        set_paused(False)
    elif administrative:
        sid = opened['scope']['session_id']
        created = client.post(f'/api/v1/harness/sessions/{sid}/send', headers=headers['subject'],
            json=dict(idempotency_key='admin-crash-turn', payload=dict(text='Captured administrative response.'))).json()
    else:
        created = send(setup, patches)
    if not queued:
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
