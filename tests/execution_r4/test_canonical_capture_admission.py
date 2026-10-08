"""Capture faults fence admission until independent recovery completes."""
import asyncio
import json
import threading
import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_native_protocol_regressions import install_native, events
from test_canonical_session_close import opened, replay
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_agent_recovery_isolation import eventually


def send_from_separate_process(setup):
    import socket
    from types import SimpleNamespace
    import uvicorn
    from runtime_http_client import process_tool
    deps, app, client, headers, *_, root = setup
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    address = f'http://127.0.0.1:{sock.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='error'))
    async def serve():
        await server.serve(sockets=[sock])
    running = client.portal.start_task_soon(serve)
    try:
        eventually(lambda: server.started)
        key = headers['operator']['Authorization'].removeprefix('Bearer ')
        runtime = (deps, SimpleNamespace(base_url=address), str(root), None, key, key)
        return process_tool(runtime, 'message_create', dict(project_root=str(root),
            from_agent_id='operator', subject='Capture failure', body='Retained independent message',
            target=dict(strategy='direct', agent_id='subject')))
    finally:
        server.should_exit = True
        running.result(timeout=10)
        sock.close()


@pytest.mark.parametrize('transport', ['mcp', 'http_process'])
@pytest.mark.parametrize('fault', ['write', 'quota'])
def test_core_capture_failure_fences_subject_then_recovers_without_replay(connected_local, monkeypatch, fault, transport):
    setup, binding, _ = connected_local
    deps, app, client, headers, *_ = setup
    peers, log = install_native(connected_local, _FAKE_SERVER_SOURCE)
    enable(setup, binding)
    sid = opened(setup, binding, 'capture-failure-open')
    first = admit(setup, binding, 'before-capture-failure', 'turn.submit', session_id=sid, text='Before storage fault')
    wait_receipt(setup, first, stages=('SUCCEEDED',))
    owner = app.state.embedded_dispatch_owner
    async def journal_of():
        return (await owner.sessions[sid]['executor']._runtime())._journal
    journal = client.portal.call(journal_of)
    if fault == 'write':
        journal._run_sync(lambda db: db.execute("CREATE TRIGGER fixture_capture_failure BEFORE INSERT ON events "
            "WHEN json_extract(CAST(NEW.body AS TEXT),'$.category')='text_delta' "
            "BEGIN SELECT RAISE(ABORT,'fixture durable capture failure'); END"))
    else:
        from nexus_connector_core.journal import JournalLimits
        original_record, original_limits = journal.record_event, journal.limits
        async def quota_at_capture(event):
            if event.category != 'text_delta':
                return await original_record(event)
            # Reach actual native output capture, after turn admission. A
            # separate test covers quota refusal before the native frontier.
            journal.limits = JournalLimits(total_event_rows=2, reserved_event_rows=1)
            try:
                return await original_record(event)
            finally:
                journal.limits = original_limits
        monkeypatch.setattr(journal, 'record_event', quota_at_capture)
    entered, release = threading.Event(), threading.Event()
    contain = owner.agents._contain
    async def held_containment(agent_id):
        entered.set()
        while not release.is_set():
            await asyncio.sleep(.01)
        return await contain(agent_id)
    monkeypatch.setattr(owner.agents, '_contain', held_containment)
    try:
        failed = admit(setup, binding, 'failed-capture-turn', 'turn.submit', session_id=sid, text='Uncaptured native output')
        assert entered.wait(15)
        assert 'subject' in owner.agents.blocked and owner.failure is None
        repeated = replay(setup, first)
        assert repeated['operation_id'] == first['operation_id']
        assert wait_receipt(setup, repeated, stages=('SUCCEEDED',))['executor_stage'] == 'SUCCEEDED'
        denied = client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json=dict(
            client_intent_id='storage-fault-new-open', intent='runtime.start', binding_id=binding['binding_id'],
            workspace_binding_id=binding['workspace_binding_id'], new_session=True))
        assert denied.status_code == 200 and not denied.json()['can_submit'], denied.text
        def counts():
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return {table: uow.connection.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                    for table in ('execution_operations', 'messages', 'message_deliveries', 'delivery_outbox')}
        before = counts()
        command = client.post('/api/v1/harness/sessions/' + sid + '/send', headers=headers['operator'],
            json={'payload': {'text': 'No admission during capture failure'}, 'idempotency_key': 'capture-fenced-command'})
        assert command.status_code == 409, command.text
        assert counts() == before
        message = send(setup, monkeypatch) if transport == 'mcp' else send_from_separate_process(setup)
        assert message['ok'] and not message['data'].get('runtime_operations'), message
        after = counts()
        assert after['execution_operations'] == before['execution_operations']
        assert after['delivery_outbox'] == before['delivery_outbox']
        assert after['messages'] == before['messages'] + 1
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT count(*) FROM runtime_pending_deliveries').fetchone()[0] == 1
        assert len(peers) == 1
        assert not [e for e in events(setup) if e.get('operation_id') == failed['operation_id']
                    and e['payload'].get('delivery_phase') == 'terminal']
    finally:
        release.set()
    eventually(lambda: 'subject' not in owner.agents.blocked, seconds=30)
    assert peers[0]._transport._proc.wait(timeout=5) is not None
    # The durable pending message resumes automatically after containment;
    # no new native intent was admitted while its event journal was faulty.
    def recovered_turn():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT operation_id,session_id FROM execution_operations "
                "WHERE action='turn.submit' AND operation_id NOT IN (?,?)",
                (first['operation_id'], failed['operation_id'])).fetchone()
            return dict(row) if row else None
    eventually(recovered_turn, seconds=30)
    sent = recovered_turn()
    second = sent['session_id']
    wait_receipt(setup, sent, stages=('SUCCEEDED',))
    assert len(peers) == 2
    wire = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert sum(event.get('method') == 'turn/start' for event in wire) == 3
    wait_receipt(setup, admit(setup, binding, 'capture-recovered-close', 'runtime.close', session_id=second), stages=('SUCCEEDED',))


def test_core_quota_compacts_acked_events_and_preserves_server_history(connected_local):
    from nexus_connector_core.journal import JournalLimits
    setup, binding, _ = connected_local
    peers, log = install_native(connected_local, _FAKE_SERVER_SOURCE)
    sid = opened(setup, binding, 'quota-open')
    first = admit(setup, binding, 'quota-first-turn', 'turn.submit', session_id=sid, text='First retained response')
    wait_receipt(setup, first, stages=('SUCCEEDED',))
    eventually(lambda: any(e.get('operation_id') == first['operation_id'] and e['payload'].get('delivery_phase') == 'terminal' for e in events(setup)))
    owner = setup[1].state.embedded_dispatch_owner
    async def journal_of():
        return (await owner.sessions[sid]['executor']._runtime())._journal
    journal = setup[2].portal.call(journal_of)
    prefix = events(setup)
    # The first committed Server page is acknowledged by the normal publisher.
    # Keep only six productive rows; the next real turn must reclaim old ACKs.
    journal.limits = JournalLimits(total_event_rows=8, reserved_event_rows=2)
    second = admit(setup, binding, 'quota-second-turn', 'turn.submit', session_id=sid, text='Second response after compaction')
    wait_receipt(setup, second, stages=('SUCCEEDED',))
    eventually(lambda: any(e.get('operation_id') == second['operation_id'] and e['payload'].get('delivery_phase') == 'terminal' for e in events(setup)))
    history = events(setup)
    assert history[:len(prefix)] == prefix
    assert len(history) > 8
    assert journal._run_sync(lambda db: db.execute('SELECT count(*) FROM events').fetchone()[0]) <= 8
    assert [e['sequence'] for e in history] == list(range(1, len(history) + 1))
    assert len(peers) == 1 and not owner.agents.blocked
    wait_receipt(setup, admit(setup, binding, 'quota-close', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))


def test_prewrite_quota_refusal_keeps_healthy_harness_available(connected_local):
    from dataclasses import replace
    setup, binding, _ = connected_local
    peers, log = install_native(connected_local, _FAKE_SERVER_SOURCE)
    sid = opened(setup, binding, 'admission-quota-open')
    first = admit(setup, binding, 'admission-quota-first', 'turn.submit', session_id=sid, text='Before capacity pressure')
    wait_receipt(setup, first, stages=('SUCCEEDED',))
    owner = setup[1].state.embedded_dispatch_owner
    async def journal_of():
        return (await owner.sessions[sid]['executor']._runtime())._journal
    journal = setup[2].portal.call(journal_of)
    original_limits = journal.limits
    count = journal._run_sync(lambda db: db.execute('SELECT count(*) FROM operations_v2').fetchone()[0])
    journal.limits = replace(original_limits, max_operation_rows=count + 1, reserved_operation_rows=1)
    try:
        refused = admit(setup, binding, 'admission-quota-refused', 'turn.submit', session_id=sid, text='Must never reach native')
        receipt = wait_receipt(setup, refused, stages=('FAILED',))
        assert receipt['possible_effect'] is False and receipt['retry_safe'] is True
        assert journal._run_sync(lambda db: db.execute('SELECT count(*) FROM operations_v2').fetchone()[0]) == count
        assert owner.failure is None and not owner.agents.blocked
        assert peers[0]._transport._proc.poll() is None
    finally:
        journal.limits = original_limits
    assert wait_receipt(setup, replay(setup, refused), stages=('FAILED',)) == receipt
    following = admit(setup, binding, 'admission-quota-restored', 'turn.submit', session_id=sid, text='After capacity returns')
    wait_receipt(setup, following, stages=('SUCCEEDED',))
    wire = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert sum(event.get('method') == 'turn/start' for event in wire) == 2
    assert len(peers) == 1 and not owner.agents.blocked
    wait_receipt(setup, admit(setup, binding, 'admission-quota-close', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))
