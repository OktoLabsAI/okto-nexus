"""A diagnostic writer timeout must not turn publication lag into host failure."""
import threading
import time

import pytest

from okto_nexus.errors import ErrorCode, OktoNexusError
from test_embedded_dispatch import local_setup, connect_local, qualified_contract, admit, wait_receipt


@pytest.mark.parametrize('local_setup', ['codex_app_server', 'claude_stream', 'pi_rpc'], indirect=True)
def test_receipt_and_diagnostic_contention_preserve_native_and_retry(local_setup, monkeypatch, caplog):
    from okto_nexus.bootstrap import embedded_dispatch
    setup, binding, native = connect_local(local_setup)
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    opened = admit(setup, binding, 'before-diagnostic-contention', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    pump, maintenance = owner.pump, owner.maintenance
    allow, diagnostic_finished = threading.Event(), threading.Event()
    original_receipt = embedded_dispatch.append_execution_receipt
    original_notice = owner._recovery_event
    original_uow = owner.factory.unit_of_work
    diagnostic_thread = threading.local()
    attempts = []

    def receipt(*args, **kwargs):
        if not allow.is_set():
            attempts.append(kwargs['frame']['operation_id'])
            raise OktoNexusError(ErrorCode.DB_ERROR, 'Fixture publication writer timeout', {}, retryable=True)
        return original_receipt(*args, **kwargs)

    def uow(*args, **kwargs):
        result = original_uow(*args, **kwargs)
        if getattr(diagnostic_thread, 'active', False):
            result._busy_timeout_ms = 25
        return result

    def notice(code, message, **kwargs):
        if code != 'RECOVERY_PUBLICATION_DELAYED':
            return original_notice(code, message, **kwargs)
        gate = owner.factory._writer_gate
        gate.acquire(5)
        diagnostic_thread.active = True
        try:
            # Real FIFO admission timeout, not an injected diagnostic exception.
            return original_notice(code, message, **kwargs)
        finally:
            diagnostic_thread.active = False
            gate.release()
            diagnostic_finished.set()

    monkeypatch.setattr(embedded_dispatch, 'append_execution_receipt', receipt)
    monkeypatch.setattr(owner.factory, 'unit_of_work', uow)
    monkeypatch.setattr(owner, '_recovery_event', notice)
    try:
        turn = admit(setup, binding, 'diagnostic-contention', 'turn.submit',
            session_id=opened['session_id'], text='One effect despite two storage failures')
        assert diagnostic_finished.wait(10)
        deadline = time.monotonic() + 10
        while len(attempts) < 2:
            assert owner.failure is None
            assert time.monotonic() < deadline
            time.sleep(.02)
        assert owner.failure is None and not owner._stopping.is_set()
        assert owner.pump is pump and owner.maintenance is maintenance
        assert not pump.task.done() and not maintenance.done()
        assert not native.native.stopped and len(native.native.sent) == 1
        assert not owner.agents.blocked
        assert 'diagnostic was not persisted' in caplog.text
        with deps.connection_factory.unit_of_work(write=False) as transaction:
            assert transaction.connection.execute("SELECT control_state FROM execution_executors WHERE kind='embedded'").fetchone()[0] == 'CONTROL_READY'
    finally:
        allow.set()
    wait_receipt(setup, turn)
    assert set(attempts) == {turn['operation_id']}
    assert not native.native.stopped and len(native.native.sent) == 1
    fresh = admit(setup, binding, 'after-diagnostic-contention', 'runtime.start', new_session=True)
    wait_receipt(setup, fresh)
    assert native.opens == 2
    with deps.connection_factory.unit_of_work(write=False) as transaction:
        assert transaction.connection.execute('SELECT MAX(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1


def test_nonretryable_diagnostic_failure_is_not_hidden(local_setup, monkeypatch):
    owner = local_setup[1].state.embedded_dispatch_owner
    def broken(*args, **kwargs):
        raise OktoNexusError(ErrorCode.DB_ERROR, 'Permanent failure', {}, retryable=False)
    monkeypatch.setattr(owner.factory, 'unit_of_work', broken)
    try:
        with pytest.raises(OktoNexusError):
            owner._recovery_event('RECOVERY_PUBLICATION_DELAYED', 'Diagnostic')
    finally:
        monkeypatch.undo()


def test_manual_recovery_does_not_report_stopped_host_ready(local_setup):
    setup, binding, _ = connect_local(local_setup)
    owner = setup[1].state.embedded_dispatch_owner
    client = setup[2]
    opened = admit(setup, binding, 'before-host-stop', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    owner.failure = OktoNexusError(ErrorCode.DB_ERROR, 'Permanent failure', {}, retryable=False)
    client.portal.call(owner.failed)
    view = client.portal.call(owner.retry_recovery)
    assert view['state'] == 'RECOVERING'
    assert view['error_code'] == ErrorCode.DB_ERROR
