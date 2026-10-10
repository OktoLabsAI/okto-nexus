"""Only durable no-spawn refusals may leave other embedded sessions running."""
import time
from contextlib import contextmanager

import pytest
from nexus_connector_core import CoreError, LocalRuntimeCore
from test_embedded_dispatch import (
    local_setup, connected_local, qualified_contract, admit, wait_receipt,
)
from test_embedded_inventory import app_for
from fastapi.testclient import TestClient


@pytest.mark.parametrize('proof', ['not_sent', 'possible_effect', 'missing_receipt'])
def test_open_drift_requires_durable_no_effect_proof(connected_local, monkeypatch, proof):
    setup, binding, native = connected_local
    deps, app, client, headers, *_ = setup
    owner = app.state.embedded_dispatch_owner
    first = admit(setup, binding, 'healthy-open', 'runtime.start', new_session=True)
    wait_receipt(setup, first)
    first_session = first['scope']['session_id']

    async def refuse(*args, **kwargs):
        raise CoreError('PROFILE_DRIFT', 'environment', retry_safe=True,
                        possible_effect=proof == 'possible_effect')

    with monkeypatch.context() as patch:
        if proof != 'not_sent':
            # Inject at the runtime boundary: no native process exists in
            # these safety cases. A real unknown native outcome deliberately
            # retains ownership and cannot be drained by a test fixture.
            patch.setattr(LocalRuntimeCore, 'open', refuse)
        else:
            patch.setattr(native, 'open', refuse)
        rejected = admit(setup, binding, 'drift-open', 'runtime.start', new_session=True)
        if proof != 'not_sent':
            until = time.monotonic() + 15
            while 'subject' not in owner.agents.errors:
                assert time.monotonic() < until
                time.sleep(.02)
            assert owner.agents.errors['subject'].code == 'PROFILE_DRIFT'
            assert owner.failure is None
            assert not owner._stopping.is_set()
            return
        view = wait_receipt(setup, rejected, stages=('FAILED',))
        assert view['possible_effect'] is False
        assert view['retry_safe'] is True
        until = time.monotonic() + 15
        while rejected['scope']['session_id'] in owner.sessions:
            assert owner.failure is None, repr(owner.failure)
            assert time.monotonic() < until
            time.sleep(.02)

    assert owner.failure is None and not owner._stopping.is_set()
    assert first_session in owner.sessions
    sent = admit(setup, binding, 'healthy-after-drift', 'turn.submit',
                 session_id=first_session, text='Still usable after another session was refused')
    wait_receipt(setup, sent)
    next_open = admit(setup, binding, 'new-after-drift', 'runtime.start', new_session=True)
    wait_receipt(setup, next_open)
    for index, session_id in enumerate((first_session, next_open['scope']['session_id'])):
        wait_receipt(setup, admit(setup, binding, f'close-{index}', 'runtime.close',
                                  session_id=session_id), stages=('SUCCEEDED',))
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT attempt_no FROM execution_dispatch_outbox WHERE operation_id=?',
                                     (rejected['operation_id'],)).fetchone()
        assert row[0] == 1  # No silent retry after refusal.
        scope = rejected['scope']['session_id']
        assert uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions WHERE session_id=?',
                                      (scope,)).fetchone()[:] == ('FAILED', 'CLOSED')
        assert not uow.connection.execute("SELECT 1 FROM execution_leases WHERE session_id=? AND status<>'REVOKED'",
                                          (scope,)).fetchone()


@pytest.mark.parametrize('error_code', ['PROFILE_DRIFT', 'AGENT_REVOKED', 'LEASE_EXPIRED'])
def test_failed_open_proof_survives_server_restart(tmp_path, monkeypatch, error_code):
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as setup:
        setup, binding, native = connected_local.__wrapped__(setup)
        owner = setup[1].state.embedded_dispatch_owner
        async def refuse(*args, **kwargs):
            raise CoreError(error_code, 'environment', retry_safe=True)
        monkeypatch.setattr(native, 'open', refuse)
        rejected = admit(setup, binding, 'refused-before-restart', 'runtime.start', new_session=True)
        wait_receipt(setup, rejected, stages=('FAILED',))
        until = time.monotonic()+15
        while rejected['scope']['session_id'] in owner.sessions:
            assert owner.failure is None, repr(owner.failure)
            assert time.monotonic()<until
            time.sleep(.02)
    deps, app = app_for(tmp_path/'home')
    with TestClient(app):
        owner = app.state.embedded_dispatch_owner
        assert owner.recovery_failure is None, repr(owner.recovery_failure)
        assert owner.pump is not None
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()[:] == ('FAILED','CLOSED')
