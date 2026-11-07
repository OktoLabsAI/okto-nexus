"""Real HTTP/SQLite/Core drain with a synthetic native protocol peer."""
import time
import sqlite3

import pytest
from nexus_connector_core import RuntimeEvent

from test_embedded_dispatch import admit, wait_receipt

pytest_plugins = ['test_embedded_dispatch']


def eventually(predicate, *, timeout=10):
    until = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < until
        time.sleep(.02)


def test_idle_open_drains_without_force_or_rewriting_open_receipt(connected_local):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, 'drain-idle-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT admission_state FROM execution_operations WHERE operation_id=?',
            (opened['operation_id'],)).fetchone()[0] == 'DISPATCHED'
        assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?',
            (opened['scope']['session_id'],)).fetchone()[0] == 'READY'
    response = client.post('/v1/runtime/shutdown', headers=headers['operator'], json={'timeout_seconds': .1})
    assert response.status_code in {200, 202}, response.text
    eventually(lambda: app.state.runtime_shutdown.status()['state'] == 'DRAINED')
    assert native.native.stopped and native.opens == 1 and native.native.sent == []
    assert not app.state.runtime_shutdown.status()['force_requested']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT stage FROM execution_receipts WHERE operation_id=? '
            'ORDER BY receipt_revision DESC LIMIT 1', (opened['operation_id'],)).fetchone()[0] == 'SUBMITTED'


@pytest.mark.parametrize('drift', [None, 'agent', 'grant', 'revision'])
def test_drain_keeps_approval_and_terminal_publication_until_work_completes(connected_local, drift, monkeypatch):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    deps.config.feature_hitl = True
    opened = admit(setup, binding, 'drain-approval-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    session = opened['scope']['session_id']
    turn = admit(setup, binding, 'drain-approval-turn', 'turn.submit', session_id=session, text='Synthetic task')
    wait_receipt(setup, turn)
    replies = []
    async def reply(request, decision, response):
        replies.append(decision)
    native.native.reply_native_approval = reply
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    request = dict(schema_version=1, request_id=7, request_hash='a' * 64,
        method='item/commandExecution/requestApproval',
        params={'threadId': 'native-thread', 'turnId': 'turn-from-native', 'itemId': 'item'})
    client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
        session, stream['stream_epoch'], 0, 'approval_request', request['method'],
        {'native_approval': request, 'native_approval_display': dict(request)}, turn['operation_id']))
    approvals = []
    def captured():
        rows = client.get('/api/v1/approvals', headers=headers['operator'],
            params={'workspace': binding['workspace_id'], 'status': 'pending'}).json()['data']['items']
        approvals[:] = [row for row in rows if row['action'] == 'execution.native.respond']
        return len(approvals) == 1
    eventually(captured)
    response = client.post('/v1/runtime/shutdown', headers=headers['operator'], json={'timeout_seconds': .02})
    assert response.status_code == 202 and response.json()['phase'] == 'waiting'
    assert not native.native.stopped and len(native.native.sent) == 1
    owner = app.state.embedded_dispatch_owner
    assert not owner._stopping.is_set() and not owner.pump._stopping.is_set()
    assert client.get('/healthz').status_code == 200
    for action in ('turn.submit', 'turn.steer'):
        target = {'target': {'kind': 'native_turn_id', 'expected_turn_id': 'turn-from-native'}} if action == 'turn.steer' else {}
        refused = client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json={
            'client_intent_id': 'drain-refuse-' + action, 'intent': action,
            'binding_id': binding['binding_id'], 'workspace_binding_id': binding['workspace_binding_id'],
            'session_id': session, 'text': 'Must not be admitted', **target})
        assert refused.status_code == 200, refused.text
        assert not refused.json()['can_submit']
    detail = client.get('/api/v1/approvals/' + approvals[0]['approval_id'], headers=headers['operator']).json()['data']
    proposal = detail['request_payload']['kwargs']
    decision = {key: proposal[key] for key in ('approval_key', 'expected_revision', 'request_hash', 'cas_token')}
    decision.update(client_intent_id='drain-approval-decision', decision='approve')
    assert client.post('/v1/runtime/approval-decisions', headers=headers['subject'], json=decision).status_code == 403
    if drift:
        with deps.connection_factory.unit_of_work() as uow:
            if drift == 'agent':
                uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='subject'")
            elif drift == 'grant':
                uow.connection.execute('UPDATE runtime_execution_grants SET revoked_at=?,revision=revision+1',
                                       (deps.clock.now_iso(),))
            else:
                uow.connection.execute('UPDATE execution_bindings SET binding_revision=binding_revision+1 '
                                       'WHERE binding_id=?', (binding['binding_id'],))
    confirmed = client.post('/v1/runtime/approval-decisions', headers=headers['operator'], json=decision)
    if drift:
        if drift == 'agent':
            assert confirmed.status_code == 404 and confirmed.json()['error']['code'] == 'NOT_FOUND'
        else:
            assert confirmed.status_code in {403, 409}, confirmed.text
        assert replies == [] and native.opens == 1
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_decisions').fetchone()[0] == 0
        return
    assert confirmed.status_code == 202, confirmed.text
    eventually(lambda: replies == ['accept'])
    time.sleep(.05)
    assert app.state.runtime_shutdown.status()['state'] == 'DRAINING_PENDING'
    assert not native.native.stopped  # A decision ACK is not a completed turn.
    host = app.state.embedded_core_host
    original_status = host.drain_status
    async def hold_ready_session():
        report = await original_status()
        return {**report, 'quiescent': False, 'resources': [*report['resources'],
            {'owner': 'synthetic-release-gate', 'outcome': 'pending'}]}
    monkeypatch.setattr(host, 'drain_status', hold_ready_session)
    client.portal.call(native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
        session, stream['stream_epoch'], 0, 'turn_state', 'turn/completed',
        {'delivery_phase': 'terminal', 'delivery_outcome': 'success', 'turn_id': 'turn-from-native'}, turn['operation_id']))
    def terminal_committed():
        with deps.connection_factory.unit_of_work(write=False) as uow:
            return uow.connection.execute('SELECT admission_state FROM execution_operations WHERE operation_id=?',
                (turn['operation_id'],)).fetchone()[0] == 'RESOLVED_TERMINAL'
    eventually(terminal_committed)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?',
            (session,)).fetchone()[0] == 'READY'
        assert uow.connection.execute("SELECT admission_state FROM execution_operations WHERE action='approval.decide'").fetchone()[0] == 'DISPATCHED'
    # No local-Core exemption: these are also the canonical facts available for
    # a remote executor. An ACKed decision does not stay pending after its turn.
    assert not app.state.runtime_shutdown._canonical_pending([])
    monkeypatch.setattr(host, 'drain_status', original_status)
    eventually(lambda: app.state.runtime_shutdown.status()['state'] == 'DRAINED')
    assert not app.state.runtime_shutdown.status()['force_requested']
    assert replies == ['accept'] and native.opens == 1 and len(native.native.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT stage FROM execution_receipts WHERE operation_id=? '
            'ORDER BY receipt_revision DESC LIMIT 1', (turn['operation_id'],)).fetchone()[0] == 'SUCCEEDED'
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1


def test_force_retains_uncertain_core_resources_until_release(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, 'drain-force-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    turn = admit(setup, binding, 'drain-force-turn', 'turn.submit',
                 session_id=opened['scope']['session_id'], text='Synthetic task')
    wait_receipt(setup, turn)
    original_close = native.native.close
    release = False
    async def uncertain_close():
        return await original_close() if release else 'unknown'
    monkeypatch.setattr(native.native, 'close', uncertain_close)
    response = client.post('/v1/runtime/shutdown', headers=headers['operator'], json={'timeout_seconds': .02})
    assert response.status_code == 202
    shutdown = app.state.runtime_shutdown
    task = shutdown._task
    try:
        async def decide():
            return await shutdown.request(timeout_seconds=0, force=True)
        assert client.portal.call(decide)['force_requested']
        time.sleep(.1)
        assert shutdown.status()['state'] == 'DRAINING_PENDING'
        assert app.state.embedded_core_host._runtime_tasks
        assert not native.native.stopped
        client.portal.call(decide)
        assert shutdown._task is task
    finally:
        release = True
    eventually(lambda: shutdown.status()['state'] == 'DRAINED')
    assert native.native.stopped and native.opens == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT stage FROM execution_receipts WHERE operation_id=? '
            'ORDER BY receipt_revision DESC LIMIT 1', (turn['operation_id'],)).fetchone()[0] in {'SUBMITTED', 'OUTCOME_UNKNOWN'}


def test_canonical_open_needs_positive_ready_proof_and_inventory_failure_retains_owner(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, 'drain-proof-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    owner = app.state.runtime_shutdown
    assert not owner._canonical_pending([])
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='OPEN_PENDING' WHERE session_id=?",
                               (opened['scope']['session_id'],))
    assert any(row.get('operation_id') == opened['operation_id'] for row in owner._canonical_pending([]))
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY' WHERE session_id=?",
                               (opened['scope']['session_id'],))
    original = owner._canonical_pending
    def unavailable(_scopes):
        raise sqlite3.OperationalError('synthetic inventory failure')
    monkeypatch.setattr(owner, '_canonical_pending', unavailable)
    response = client.post('/v1/runtime/shutdown', headers=headers['operator'], json={'timeout_seconds': .02})
    assert response.status_code == 202
    eventually(lambda: 'DRAIN_OBSERVATION_UNAVAILABLE' in owner.status()['error_codes'])
    assert not native.native.stopped and app.state.embedded_core_host._runtime_tasks
    monkeypatch.setattr(owner, '_canonical_pending', original)
    eventually(lambda: owner.status()['state'] == 'DRAINED')
    assert native.native.stopped
