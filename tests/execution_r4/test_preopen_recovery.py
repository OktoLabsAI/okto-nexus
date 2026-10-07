import asyncio
import time
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from nexus_connector_core import CoreError, LocalRuntimeCore, SQLiteOwnedSlotLedger, OperationKey
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_embedded_inventory import app_for


@pytest.mark.parametrize('occupied', [False, True])
def test_preopen_failure_recovers_only_with_empty_owned_resources(tmp_path, monkeypatch, occupied):
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as setup:
        setup, binding, native = connected_local.__wrapped__(setup)
        deps, app, client, headers, *_ = setup
        async def fail_prepare(*args, **kwargs):
            raise CoreError('BINDING_NOT_AUTHORIZED', 'prepare')
        with monkeypatch.context() as patch:
            patch.setattr(LocalRuntimeCore, 'prepare', fail_prepare)
            opened = admit(setup, binding, 'before-native-open', 'runtime.start', new_session=True, text='Hello')
            owner = app.state.embedded_dispatch_owner
            until = time.monotonic() + 8
            while 'subject' not in owner.agents.errors:
                assert time.monotonic() < until
                time.sleep(.02)
            channel = owner.channel
            assert native.opens == 0
    if occupied:
        async def occupy():
            ledger = SQLiteOwnedSlotLedger(tmp_path / 'home/core-runtime/owned-slots.db')
            try:
                await ledger.reserve_owned_slot(OperationKey(channel.server_id, channel.executor_id, 'other-open'), 'other-session')
            finally:
                await ledger.aclose()
        asyncio.run(occupy())
    deps, app = app_for(tmp_path / 'home')
    with TestClient(app) as client:
        owner = app.state.embedded_dispatch_owner
        if occupied:
            assert owner.recovery_failure is not None and owner.pump is None
            return
        assert owner.recovery_failure is None, repr(owner.recovery_failure)
        assert owner.pump is not None
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()) == ('FAILED', 'CLOSED')
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts').fetchone()[0] == 0
            assert all(row[0] == 'RESOLVED_TERMINAL' for row in uow.connection.execute('SELECT admission_state FROM execution_operations'))
        owner.native_factory = native
        next_setup = (deps, app, client, headers, *setup[4:])
        next_open = admit(next_setup, binding, 'after-preopen-recovery', 'runtime.start', new_session=True)
        wait_receipt(next_setup, next_open)
        assert native.opens == 1
        wait_receipt(next_setup, admit(next_setup, binding, 'recovered-close', 'runtime.close',
                                      session_id=next_open['session_id']), stages=('SUCCEEDED',))
