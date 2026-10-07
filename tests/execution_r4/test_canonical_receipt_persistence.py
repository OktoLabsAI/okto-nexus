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
