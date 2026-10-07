"""Fault injection through real lifecycle, journals, HTTP setup and WSS ingress."""
import asyncio
from contextlib import contextmanager
import time
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from nexus_connector_core import R4_PREVIEW_REVISION, encode_r4_frame

from test_embedded_dispatch import local_setup, connect_local, admit, wait_receipt, qualified_contract
from test_embedded_inventory import app_for


def eventually(check, seconds=10):
    deadline = time.monotonic() + seconds
    while not check():
        assert time.monotonic() < deadline, 'Automatic recovery did not converge'
        time.sleep(.02)


def create_agent(setup, agent_id):
    deps, app, client, headers, body, candidate, root = setup
    created = client.post('/api/v1/agents', headers=headers['operator'], json={'agent_id': agent_id})
    assert created.status_code == 200, created.text
    agent_headers = dict(headers, subject={'Authorization': 'Bearer ' + created.json()['data']['api_key']})
    return (deps, app, client, agent_headers,
            dict(body, agent_id=agent_id, client_intent_id='setup-' + agent_id), candidate, root)


def remote_roundtrip(setup, agent_id):
    from test_connection_setup import request_for
    from okto_nexus.application.connection_setup import load_setup
    from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket
    from okto_nexus.adapters.inbound.http.executor_link import protocol_info
    deps, app, client, headers, *_ = setup
    context, request = request_for(setup)
    request.update(agent_id=agent_id, client_intent_id='remote-' + agent_id,
        executor_id='', candidate_ref='', inventory_revision='',
        baseline=load_setup(deps, context, agent_id)['baseline'])
    request['configuration']['execution_location'] = 'remote'
    response = client.post('/v1/connections/setup:finish', headers=headers['operator'], json=request)
    assert response.status_code == 200, response.text
    response = client.post('/v1/connections/executors:register', headers=headers['subject'], json={
        'client_intent_id': 'register-' + agent_id, 'connector_id': 'connector-' + agent_id,
        'label': agent_id, 'control_capabilities': []})
    assert response.status_code in (200, 201), response.text
    registered = response.json()
    server, executor = registered['server_id'], registered['executor_id']
    info = protocol_info()
    # Exercise three real socket disconnect/reconnect handshakes while a local
    # subject is blocked. No stubbed dispatcher or global readiness bypass.
    for index in range(3):
        ticket = issue_execution_ticket(deps.connection_factory, server_id=server, executor_id=executor,
            binding_id=None, agent_id=agent_id).ticket
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
                headers={'Authorization': 'Bearer ' + ticket}, subprotocols=['nxl.v1']) as ws:
            base = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, server_id=server, executor_id=executor)
            ws.send_text(encode_r4_frame(dict(base, type='hello', link_attempt_id=f'reconnect-{index}',
                core_version=info['core_version'], management_revision=info['management_revision'],
                supported_nxl=[R4_PREVIEW_REVISION], snapshot_formats=[info['executor_snapshot_format']],
                control_capabilities=['heartbeat_ack_v1'])).decode())
            welcome = ws.receive_json()
            assert welcome['type'] == 'welcome'
            base.update(connection_id=welcome['connection_id'], connection_generation=welcome['connection_generation'])
            request = ws.receive_json()
            assert request['operation_ids'] == request['session_ids'] == []
            ws.send_text(encode_r4_frame(dict(base, type='reconcile.report', reconcile_id=request['reconcile_id'],
                cursor=None, next_cursor=None, complete=True, receipts=[], claims=[],
                stream_watermarks=[], ownership_facts=[])).decode())
            assert ws.receive_json()['recovery_remaining'] is False
            ws.send_text(encode_r4_frame(dict(base, type='heartbeat')).decode())
            assert ws.receive_json()['type'] == 'heartbeat'


@pytest.mark.parametrize('fault', ['unavailable', 'hung'])
def test_restart_isolates_fault_and_accepts_new_local_and_remote_agents(tmp_path, monkeypatch, fault):
    from okto_nexus.bootstrap.embedded_events import EmbeddedEventPublisher
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as setup:
        setup, binding, first_native = connect_local(setup)
        opened = admit(setup, binding, 'before-restart', 'runtime.start', new_session=True)
        wait_receipt(setup, opened)
        healthy_setup = create_agent(setup, 'healthy')
        healthy_setup, healthy_binding, healthy_native = connect_local(healthy_setup, agent_id='healthy')
        healthy = admit(healthy_setup, healthy_binding, 'healthy-before', 'runtime.start', new_session=True)
        wait_receipt(healthy_setup, healthy)
    original = EmbeddedEventPublisher.step
    release = asyncio.Event()
    fault_enabled = True
    calls = 0

    async def faulty(publisher, scope):
        nonlocal calls
        if scope['agent_id'] == 'subject' and fault_enabled:
            calls += 1
            if fault == 'hung':
                await release.wait()
            else:
                raise OSError('Temporary journal unavailable for one agent')
        return await original(publisher, scope)

    monkeypatch.setattr(EmbeddedEventPublisher, 'step', faulty)
    deps, app = app_for(tmp_path / 'home')
    with TestClient(app) as client:
        owner = app.state.embedded_dispatch_owner
        current = (deps, app, client, setup[3], *setup[4:])
        try:
            assert owner.pump is not None and owner.failure is None
            assert 'subject' in owner.agents.blocked
            eventually(lambda: 'healthy' not in owner.agents.blocked)
            # A configured healthy agent starts again while the old peer waits.
            restored = (deps, app, client, healthy_setup[3], *healthy_setup[4:])
            owner.native_factory = healthy_native
            wait_receipt(restored, admit(restored, healthy_binding, 'healthy-after', 'runtime.start', new_session=True))
            newcomer = create_agent(current, 'new-local')
            newcomer, new_binding, new_native = connect_local(newcomer, agent_id='new-local')
            wait_receipt(newcomer, admit(newcomer, new_binding, 'new-during-recovery', 'runtime.start', new_session=True))
            remote_roundtrip(create_agent(current, 'new-remote'), 'new-remote')
            listing = client.get('/api/v1/agents', headers=current[3]['operator']).json()['data']['items']
            statuses = {r['agent_id']: r['connection']['status'] for r in listing}
            assert statuses['subject'] == 'Recovering'
            assert statuses['healthy'] == statuses['new-local'] == 'Ready'
            if fault == 'hung':
                assert calls == 1, 'A slow worker must never be duplicated'
            else:
                archived = client.delete('/api/v1/agents/subject', headers=current[3]['operator'])
                assert archived.status_code == 200, archived.text
            # Remove only the injected fault. No user retry, restart or reset.
            fault_enabled = False
            client.portal.call(release.set)
            eventually(lambda: 'subject' not in owner.agents.blocked, seconds=15)
            assert owner.failure is None and first_native.opens == 1
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?',
                    (opened['session_id'],)).fetchone()[0] == 'CLOSED'
                assert uow.connection.execute('SELECT MAX(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1
                if fault == 'unavailable':
                    assert uow.connection.execute("SELECT is_active FROM agents WHERE agent_id='subject'").fetchone()[0] == 0
        finally:
            fault_enabled = False
            client.portal.call(release.set)
    # Repeat the full server lifecycle with all identities retained.
    for _ in range(3):
        deps, app = app_for(tmp_path / 'home')
        with TestClient(app):
            owner = app.state.embedded_dispatch_owner
            eventually(lambda: not owner.agents.blocked)
            assert owner.pump is not None and owner.failure is None
            assert not owner.host._runtime_tasks, 'Restart must not replay previous work'


def test_live_event_failure_contains_only_its_agent_and_restores_automatically(local_setup, monkeypatch):
    from nexus_connector_core import RuntimeEvent
    from okto_nexus.bootstrap import embedded_events
    setup, binding, native = connect_local(local_setup)
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    first = admit(setup, binding, 'live-first', 'runtime.start', new_session=True)
    wait_receipt(setup, first)
    other = create_agent(setup, 'other-live')
    other, other_binding, other_native = connect_local(other, agent_id='other-live')
    second = admit(other, other_binding, 'live-second', 'runtime.start', new_session=True)
    wait_receipt(other, second)
    original = embedded_events.commit_execution_events
    enabled = True
    def fail_one(*args, **kwargs):
        if enabled and kwargs['frame']['agent_id'] == 'subject':
            raise OSError('One subject event projection unavailable')
        return original(*args, **kwargs)
    monkeypatch.setattr(embedded_events, 'commit_execution_events', fail_one)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams WHERE agent_id=?', ('subject',)).fetchone())
    client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
        stream['session_id'], stream['stream_epoch'], 0, 'text_delta', 'technical.output', {'text': 'Retained once'}))
    eventually(lambda: 'subject' in owner.agents.blocked)
    eventually(lambda: native.native.stopped)
    wait_receipt(other, admit(other, other_binding, 'unaffected-turn', 'turn.submit',
        session_id=second['session_id'], text='Still available'))
    assert not other_native.native.stopped and owner.failure is None
    enabled = False
    eventually(lambda: 'subject' not in owner.agents.blocked, seconds=15)
    wait_receipt(setup, admit(setup, binding, 'restored-new-session', 'runtime.start', new_session=True))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_event_ingress').fetchone()[0] == 1
        assert uow.connection.execute('SELECT MAX(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1


def test_close_publishes_last_captured_event_before_retiring_stream(local_setup, monkeypatch):
    from nexus_connector_core import RuntimeEvent
    setup, binding, native = connect_local(local_setup)
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    opened = admit(setup, binding, 'last-event-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    original_close = native.native.close
    async def close_with_capture():
        _, journal = await owner.host._runtime_tasks[(stream['executor_id'], stream['session_id'])]
        await journal.append_event(RuntimeEvent(stream['server_id'], stream['executor_id'], stream['session_id'],
            stream['stream_epoch'], 1, 'text_delta', 'technical.output', {'text': 'Last captured event'}))
        return await original_close()
    monkeypatch.setattr(native.native, 'close', close_with_capture)
    wait_receipt(setup, admit(setup, binding, 'last-event-close', 'runtime.close',
        session_id=opened['session_id']), stages=('SUCCEEDED',))
    def drained():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute('SELECT drained FROM execution_local_streams').fetchone()[0] == 1
    eventually(drained)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_event_ingress').fetchone()[0] == 1
        assert uow.connection.execute('SELECT committed_contiguous FROM execution_event_watermarks').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_local_publications WHERE terminal=0').fetchone()[0] == 0


@pytest.mark.parametrize('local_setup', ['codex_app_server', 'claude_stream', 'pi_rpc'], indirect=True)
def test_slow_publication_keeps_native_and_lease_alive(local_setup, monkeypatch):
    from okto_nexus.bootstrap.embedded_events import EmbeddedEventPublisher
    from test_sender_sessions import Peers, configure, sender, turn_for, complete
    setup, binding, _ = connect_local(local_setup)
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    peers = Peers()
    owner.native_factory = peers
    configure(setup, binding, 'per_sender')
    turn = turn_for(setup, sender(setup, monkeypatch)('operator'))
    wait_receipt(setup, turn)
    renewal_errors = []
    original_issue = owner.leases.issue
    def observe_issue(*args, **kwargs):
        try:
            return original_issue(*args, **kwargs)
        except Exception as error:
            renewal_errors.append(str(error))
            raise
    monkeypatch.setattr(owner.leases, 'issue', observe_issue)
    owner.agents.observation_timeout = .15
    release = asyncio.Event()
    entered = asyncio.Event()
    original = EmbeddedEventPublisher.step
    calls = 0
    async def slow(publisher, scope):
        nonlocal calls
        if scope['session_id'] == turn['session_id']:
            calls += 1
            entered.set()
            await release.wait()
        return await original(publisher, scope)
    monkeypatch.setattr(EmbeddedEventPublisher, 'step', slow)
    try:
        eventually(entered.is_set)
        eventually(lambda: 'subject' in owner.agents.delayed)
        def serial():
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return uow.connection.execute('SELECT MAX(lease_serial) FROM execution_leases WHERE session_id=?',
                    (turn['session_id'],)).fetchone()[0]
        # Drive real maintenance renewals while publication is suspended;
        # do not make this test depend on sub-second CI scheduling margins.
        for _ in range(2):
            previous = serial()
            client.portal.call(lambda: owner.sessions[turn['session_id']].update(renew_at=time.monotonic()))
            def renewed():
                assert not renewal_errors, renewal_errors
                task = owner.sessions[turn['session_id']].get('renew_task')
                return serial() > previous and task is not None and task.done()
            eventually(renewed)
        assert calls == 1, 'A retained observer must never be duplicated'
        assert 'subject' not in owner.agents.blocked
        assert not peers.sessions[turn['session_id']].stopped
        assert serial() >= 3
    finally:
        client.portal.call(release.set)
    complete(setup, peers, turn, 'Response survived publication lag')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute('SELECT 1 FROM execution_delivery_releases').fetchone()


@pytest.mark.parametrize('local_setup', ['codex_app_server', 'claude_stream', 'pi_rpc'], indirect=True)
def test_released_incomplete_turn_does_not_block_next_message(local_setup, monkeypatch):
    from nexus_connector_core import RuntimeEvent
    from okto_nexus.bootstrap import embedded_events
    from test_sender_sessions import Peers, configure, sender, turn_for, complete
    setup, binding, _ = connect_local(local_setup)
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    peers = Peers()
    owner.native_factory = peers
    configure(setup, binding, 'per_sender')
    send = sender(setup, monkeypatch)
    first = turn_for(setup, send('operator'))
    wait_receipt(setup, first)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    original = embedded_events.commit_execution_events
    broken = True
    def fail(*args, **kwargs):
        if broken:
            raise OSError('Temporary publication failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(embedded_events, 'commit_execution_events', fail)
    client.portal.call(peers.sessions[first['session_id']].queue.put, RuntimeEvent(
        stream['server_id'], stream['executor_id'], stream['session_id'], stream['stream_epoch'], 0,
        'text_delta', 'fixture.output', dict(output_text='Partial response'), operation_id=first['operation_id']))
    try:
        eventually(lambda: 'subject' in owner.agents.blocked)
        eventually(lambda: peers.sessions[first['session_id']].stopped)
    finally:
        broken = False
    eventually(lambda: 'subject' not in owner.agents.blocked, seconds=15)
    second = turn_for(setup, send('operator', 'A new message'))
    assert second['session_id'] != first['session_id']
    wait_receipt(setup, second)
    complete(setup, peers, second, 'Recovered response')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        row = conn.execute('SELECT d.* FROM delivery_outbox d JOIN execution_delivery_releases r '
            'ON r.domain_operation_id=d.operation_id WHERE r.operation_id=?', (first['operation_id'],)).fetchone()
        assert row['status'] == 'OUTCOME_UNKNOWN'
        assert row['reason'] == 'session_released_without_result'
        assert row['canonical_terminal_operation_id'] is None
        assert conn.execute('SELECT stage FROM execution_receipts WHERE operation_id=? ORDER BY receipt_revision DESC',
            (first['operation_id'],)).fetchone()[0] == 'SUBMITTED'
        assert conn.execute('SELECT terminal_sequence FROM execution_results WHERE operation_id=?',
            (first['operation_id'],)).fetchone()[0] is None
        assert conn.execute('SELECT MAX(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    # Reproduce retained state from before this fix: the stream was retired,
    # but no separate delivery release was recorded. Recovery must repair it
    # from Core proofs, without requiring the operator to edit the database.
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('DELETE FROM execution_delivery_releases')
        uow.connection.execute("UPDATE delivery_outbox SET status='ACCEPTED',reason=NULL WHERE operation_id=?",
            (row['operation_id'],))
    client.portal.call(owner.agents.fail, 'subject', OSError('Recovery of retained legacy state'))
    eventually(lambda: 'subject' not in owner.agents.blocked, seconds=15)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_delivery_releases').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_results WHERE canonical_operation_id=?',
            (first['operation_id'],)).fetchone()[0] == 0


def test_live_publication_yields_even_when_stream_keeps_growing():
    from okto_nexus.bootstrap.embedded_events import EmbeddedEventPublisher
    publisher = EmbeddedEventPublisher(None)
    calls = []
    publisher._page = lambda **kw: [{'rowid': 1}] if kw['after'] == 0 else []
    async def growing(scope):
        calls.append(scope['rowid'])
        return True  # Native output never reaches an empty tail in this pass.
    publisher.step = growing
    asyncio.run(publisher.recover(live_only=True))
    assert calls == [1]


@pytest.mark.skipif(sys.platform != 'win32', reason='Actual Windows Job crash containment')
@pytest.mark.parametrize('termination', ['graceful', 'kill', 'kill-before-bind'])
def test_real_process_exit_restores_without_lock_reset_or_replay(tmp_path, monkeypatch, termination):
    from nexus_connector_core import InstallationCandidate
    from nexus_connector_core.discovery import fingerprint
    from okto_nexus.bootstrap import embedded_inventory
    from okto_nexus.adapters.inbound.http.lock import ServeLock
    from okto_nexus.adapters.outbound.process_liveness import process_exited
    root = tmp_path / 'disposable'
    root.mkdir()
    repo = Path(__file__).resolve().parents[2]
    fixture = Path(__file__).with_name('agent_recovery_process_fixture.py')
    import nexus_connector_core
    core_source = str(Path(nexus_connector_core.__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([
        str(repo / 'src'), core_source, str(fixture.parent), str(repo / 'tests')]), PYTHONIOENCODING='utf-8')
    with (root / 'process.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, str(fixture), str(root), 'before-bind' if termination == 'kill-before-bind' else 'running'], cwd=repo, env=env,
            stdin=subprocess.PIPE, stdout=log, stderr=log, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        try:
            def ready():
                assert process.poll() is None, (root / 'process.log').read_text(encoding='utf-8')[-4000:]
                return (root / 'ready.json').exists()
            eventually(ready, seconds=40)
            state = json.loads((root / 'ready.json').read_text(encoding='utf-8'))
            assert all(process_exited(pid) is False for pid in state['processes'])
            if termination.startswith('kill'):
                process.kill()  # exact disposable Nexus owner; Windows Jobs contain its peers
                process.wait(timeout=10)
            else:
                process.communicate('\n', timeout=30)
                assert process.returncode == 0, (root / 'process.log').read_text(encoding='utf-8')[-4000:]
            eventually(lambda: all(process_exited(pid) is True for pid in state['processes']))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    binary = root / 'codex.exe'
    candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=(candidate,)))
    started = time.monotonic()
    # Neither lock files nor leases are deleted/expired by the test.
    with ServeLock(root / 'home'):
        for cycle in range(3):
            deps, app = app_for(root / 'home')
            with TestClient(app) as client:
                owner = app.state.embedded_dispatch_owner
                eventually(lambda: not owner.agents.blocked)
                assert owner.pump is not None and owner.failure is None
                if cycle == 0:
                    assert time.monotonic() - started < 20, 'Dead owner must not require the 40/60 second lease timeout'
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    assert uow.connection.execute("SELECT COUNT(*) FROM execution_sessions WHERE lifecycle_state NOT IN ('CLOSED','FAILED')").fetchone()[0] == 0
                    assert uow.connection.execute('SELECT COUNT(*) FROM execution_event_ingress').fetchone()[0] == state['expected_events']
                current = (deps, app, client, state['headers'], state['body'], candidate, root / 'workspace')
                local = create_agent(current, f'local-cycle-{cycle}')
                local, binding, native = connect_local(local, agent_id=f'local-cycle-{cycle}')
                wait_receipt(local, admit(local, binding, f'new-{cycle}', 'runtime.start', new_session=True))
                assert native.opens == 1
                if cycle == 0:
                    wait_receipt(current, admit(current, state['binding'], 'original-restored', 'runtime.start', new_session=True))
                remote_roundtrip(create_agent(current, f'remote-cycle-{cycle}'), f'remote-cycle-{cycle}')
