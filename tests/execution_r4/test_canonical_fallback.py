"""Typed legacy pre-write proof may transfer one claim into canonical admission."""
import time
import pytest
from okto_nexus.domain.runtime_commands import RuntimeCommandNotSent
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_delivery_selection import legacy
from test_canonical_consumption import pull


@pytest.mark.parametrize('outcome', ['success', 'unknown', 'revoked', 'admission_failure'])
def test_legacy_failure_fallback_uses_canonical_owner(connected_local, monkeypatch, outcome):
    setup, binding, native = connected_local
    deps = setup[0]
    enable(setup, binding)
    legacy(setup, binding, priority=99, group='reviewed-equivalence')
    owner = deps.runtime_dispatcher
    calls = []
    def refused(operation):
        calls.append(operation['endpoint_id'])
        assert operation['endpoint_id'] == 'zz-legacy', 'Canonical target entered the legacy worker'
        if outcome == 'unknown':
            raise OSError('No proof of non-delivery')
        raise RuntimeCommandNotSent('Fixture refused before native write')
    monkeypatch.setattr(owner, 'dispatch', refused)
    owner.retry_jitter = lambda: 0
    assert send(setup, monkeypatch)['ok']
    deadline = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
        if row['status'] in ('RETRY_WAIT', 'OUTCOME_UNKNOWN'):
            break
        assert time.monotonic() < deadline, row
        time.sleep(.01)
    assert calls == ['zz-legacy']
    assert pull(setup, monkeypatch) == []
    if outcome == 'unknown':
        assert row['status'] == 'OUTCOME_UNKNOWN' and row['next_binding'] is None
        assert native.opens == 0
        return
    assert row['status'] == 'RETRY_WAIT' and row['retry_basis'] == 'APPROVED_ENDPOINT_BEFORE_WRITE'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
    if outcome == 'revoked':
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agent_endpoints SET enabled=0 WHERE endpoint_id='zz-legacy'")
    if outcome == 'admission_failure':
        from okto_nexus.application import execution_domain_delivery
        from okto_nexus.errors import OktoNexusError, ErrorCode
        original = execution_domain_delivery.submit_execution_operation
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise OktoNexusError(ErrorCode.CONFLICT, 'Injected post-admission failure', {})
        monkeypatch.setattr(execution_domain_delivery, 'submit_execution_operation', fail)
    deadline = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            after = dict(uow.connection.execute('SELECT * FROM delivery_outbox').fetchone())
        if after['status'] in ('ACCEPTED', 'REJECTED'):
            break
        assert time.monotonic() < deadline, after
        time.sleep(.02)
    assert after['operation_id'] == row['operation_id'] and after['attempt_count'] == 2
    assert calls == ['zz-legacy']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
        if outcome != 'success':
            assert after['status'] == 'REJECTED'
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_domain_deliveries').fetchone()[0] == 0
            assert native.opens == 0
            return
        turn = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='turn.submit'").fetchone())
        assert after['runtime_session_id'] is None and after['endpoint_id'] == binding['endpoint_id']
        assert uow.connection.execute('SELECT consumer_kind,consumer_operation_id FROM message_deliveries').fetchone()[:] == ('push', row['operation_id'])
    wait_receipt(setup, turn)
    assert native.opens == 1 and len(native.native.sent) == 1
    assert pull(setup, monkeypatch) == []
    wait_receipt(setup, admit(setup, binding, 'fallback-close', 'runtime.close', session_id=turn['session_id']), stages=('SUCCEEDED',))
