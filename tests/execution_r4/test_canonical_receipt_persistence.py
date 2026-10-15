"""Server receipt persistence lag must not kill a healthy native session."""
import threading
import time
import sqlite3
import pytest
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt


@pytest.mark.parametrize('fault', ['io', 'sqlite', 'database'])
def test_receipt_persistence_retries_without_containment_or_native_replay(connected_local, monkeypatch, fault):
    from okto_nexus.bootstrap import embedded_dispatch
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    opened = admit(setup, binding, 'before-receipt-storage-fault', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    original = embedded_dispatch.append_execution_receipt
    attempts = []
    allow, failed = threading.Event(), threading.Event()
    def unavailable(*args, **kwargs):
        if not allow.is_set():
            attempts.append(kwargs['frame']['operation_id'])
            failed.set()
            if fault == 'database':
                from okto_nexus.errors import OktoNexusError, ErrorCode
                raise OktoNexusError(ErrorCode.DB_ERROR, 'Temporary Server receipt transaction failure', {})
            raise (OSError if fault == 'io' else sqlite3.OperationalError)('Temporary Server receipt transaction failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(embedded_dispatch, 'append_execution_receipt', unavailable)
    try:
        turn = admit(setup, binding, 'receipt-storage-fault', 'turn.submit', session_id=opened['session_id'], text='One native effect')
        assert failed.wait(10)
        until = time.monotonic() + 5
        while len(attempts) < 2 and 'subject' not in owner.agents.blocked:
            assert time.monotonic() < until
            time.sleep(.02)
        assert 'subject' not in owner.agents.blocked
        assert not native.native.stopped and len(native.native.sent) == 1
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()[:] == ('READY', 'ACTIVE')
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts WHERE operation_id=?', (turn['operation_id'],)).fetchone()[0] == 0
    finally:
        allow.set()
    wait_receipt(setup, turn)
    assert len(attempts) >= 2 and set(attempts) == {turn['operation_id']}
    assert not native.native.stopped and len(native.native.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT MAX(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1


def test_open_receipt_storage_failure_replays_rest_and_mcp_without_reopening(connected_local, monkeypatch):
    from pathlib import Path
    from okto_nexus.bootstrap import embedded_dispatch
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    setup, binding, native = connected_local
    deps, app, client, headers, *_, root = setup
    client.headers['host'] = '127.0.0.1:8000'
    key = headers['subject']['Authorization'].removeprefix('Bearer ')
    body = dict(agent_id='subject', kind='codex', project_root=str(root),
                endpoint_id=binding['endpoint_id'], idempotency_key='lost-open-receipt')
    original = embedded_dispatch.append_execution_receipt
    reached, allow = threading.Event(), threading.Event()
    def unavailable(*args, **kwargs):
        if not allow.is_set():
            reached.set()
            raise sqlite3.OperationalError('Temporary open receipt storage failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(embedded_dispatch, 'append_execution_receipt', unavailable)
    try:
        first = client.post('/api/v1/harness/sessions', headers=headers['subject'], json=body)
        assert first.status_code == 200, first.text
        assert reached.wait(10)
        assert native.opens == 1
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 0
        repeated = tool(client, key, 'harness_open', body)
        assert repeated['ok'], repeated
        assert repeated['data']['operation_id'] == first.json()['data']['operation_id']
        assert native.opens == 1 and not native.native.stopped
    finally:
        allow.set()
    wait_receipt(setup, first.json()['data'])
    replay = client.post('/api/v1/harness/sessions', headers=headers['subject'], json=body)
    assert replay.status_code == 200 and replay.json()['data']['operation_id'] == repeated['data']['operation_id']
    assert native.opens == 1 and not native.native.stopped
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM execution_sessions').fetchone()[0] == 1
        assert uow.connection.execute('SELECT max(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1
