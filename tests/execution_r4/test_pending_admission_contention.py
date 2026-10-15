"""A queue-maintenance writer timeout must not stop healthy runtime sessions."""
import threading
import time
from types import SimpleNamespace

import pytest

from okto_nexus.application import runtime_recovery
from okto_nexus.errors import ErrorCode, OktoNexusError
from test_embedded_dispatch import connected_local, admit, wait_receipt, qualified_contract
from test_local_realization import local_setup


def test_pending_queue_timeout_preserves_sessions_and_dispatches_initial_text(connected_local, monkeypatch):
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    opened = admit(setup, binding, 'before-contention', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    existing_native = native.native
    pump, maintenance = owner.pump, owner.maintenance
    recovered = threading.Event()
    original = runtime_recovery.drain_pending
    calls = []
    def contended(deps):
        calls.append(1)
        if len(calls) <= 2:
            raise OktoNexusError(ErrorCode.DB_ERROR, 'SQLite writer admission timed out.', {}, retryable=True)
        original(deps)
        recovered.set()
    monkeypatch.setattr(runtime_recovery, 'drain_pending', contended)
    assert recovered.wait(10), 'Maintenance did not retry transient storage contention'
    assert owner.failure is None and not owner._stopping.is_set()
    assert owner.pump is pump and owner.maintenance is maintenance
    assert not pump.task.done() and not maintenance.done() and not existing_native.stopped
    sent = admit(setup, binding, 'existing-after-contention', 'turn.submit',
                 session_id=opened['session_id'], text='Existing session remains available')
    wait_receipt(setup, sent)
    fresh = admit(setup, binding, 'initial-after-contention', 'runtime.start',
                  new_session=True, text='Initial text must reach the harness once')
    wait_receipt(setup, fresh)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        child = uow.connection.execute('SELECT operation_id FROM execution_operations WHERE parent_operation_id=?',
                                       (fresh['operation_id'],)).fetchone()[0]
    wait_receipt(setup, {'operation_id': child})
    assert sum(verb == 'send_turn' for verb, payload in native.native.sent) == 1
    assert owner.failure is None and native.opens == 2


def test_nonretryable_storage_failure_still_contains(connected_local, monkeypatch):
    setup, _, _ = connected_local
    owner = setup[1].state.embedded_dispatch_owner
    def broken(_):
        raise OktoNexusError(ErrorCode.DB_ERROR, 'Database unavailable', {}, retryable=False)
    monkeypatch.setattr(runtime_recovery, 'drain_pending', broken)
    deadline = time.monotonic() + 10
    # Failure is assigned before the asynchronous containment callback sets
    # its fence. Observe that fence, not the earlier diagnostic assignment.
    while not owner._stopping.is_set() and time.monotonic() < deadline:
        time.sleep(.02)
    assert isinstance(owner.failure, OktoNexusError)
    assert owner._stopping.is_set()


def test_empty_pending_queue_uses_only_read_transaction(connected_local, monkeypatch):
    deps = connected_local[0][0]
    writes = []
    original = deps.connection_factory.unit_of_work
    def uow(*, write=True):
        writes.append(write)
        return original(write=write)
    # A separate facade counts only this invocation, not background workers.
    proxy = SimpleNamespace(connection_factory=SimpleNamespace(unit_of_work=uow))
    runtime_recovery.drain_pending(proxy)
    assert writes == [False]
