"""Lease renewal cannot invalidate a control during its pre-effect persistence."""
import threading
from concurrent.futures import TimeoutError

import pytest
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt


@pytest.mark.parametrize('action', ['runtime.close', 'turn.interrupt'])
def test_control_keeps_its_context_while_renewal_waits(connected_local, monkeypatch, action):
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    opened = admit(setup, binding, 'control-renew-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    sid = opened['scope']['session_id']
    session = owner.sessions[sid]
    entered, release = threading.Event(), threading.Event()
    bind = owner._bind
    def hold(frame, *args):
        if frame['action'] == action:
            entered.set()
            assert release.wait(10)
        return bind(frame, *args)
    monkeypatch.setattr(owner, '_bind', hold)
    renewal = None
    try:
        options = {'target': {'kind': 'current_run', 'expected_turn_id': None}} if action == 'turn.interrupt' else {}
        control = admit(setup, binding, 'control-before-renew', action, session_id=sid, **options)
        assert entered.wait(10)
        renewal = client.portal.start_task_soon(owner._renew_owned, sid, session)
        # A real renewal, not a changed clock or synthetic context, competes
        # with the admitted control after its context has been selected.
        with pytest.raises(TimeoutError):
            renewal.result(timeout=.5)
    finally:
        release.set()
    wait_receipt(setup, control, stages=('SUCCEEDED',) if action == 'runtime.close' else ('SUBMITTED', 'SUCCEEDED'))
    renewal.result(timeout=10)
    assert not owner.agents.blocked and owner.failure is None
    assert native.opens == 1
    if action == 'runtime.close':
        assert native.native.stopped and sid not in owner.sessions
    else:
        assert not native.native.stopped
        assert [verb for verb, _ in native.native.sent] == ['interrupt']
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT MAX(lease_serial) FROM execution_leases').fetchone()[0] >= 2


def test_close_reaches_core_while_interrupt_waits_for_native_response(connected_local, monkeypatch):
    import asyncio
    import time
    from nexus_connector_core import OperationKey
    from test_vertical_inventory import _Native
    setup, binding, native = connected_local
    _, app, client, *_ = setup
    opened = admit(setup, binding, 'parallel-control-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    entered, release = threading.Event(), threading.Event()
    original = _Native.send
    async def hold(peer, verb, *args, **kwargs):
        result = await original(peer, verb, *args, **kwargs)
        if verb == 'interrupt':
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.01)
        return result
    monkeypatch.setattr(_Native, 'send', hold)
    try:
        admit(setup, binding, 'held-interrupt', 'turn.interrupt', session_id=opened['scope']['session_id'],
            target={'kind': 'current_run', 'expected_turn_id': None})
        assert entered.wait(10)
        closed = admit(setup, binding, 'parallel-close', 'runtime.close', session_id=opened['scope']['session_id'])
        owner = app.state.embedded_dispatch_owner
        async def receipt():
            return await owner.host.historical_receipt(session_id=opened['scope']['session_id'],
                key=OperationKey(owner.channel.server_id, owner.channel.executor_id, closed['operation_id']))
        until = time.monotonic() + 10
        while True:
            observed = client.portal.call(receipt)
            if observed is not None and observed.stage == 'SUBMISSION_STARTED':
                break
            assert time.monotonic() < until, observed
            time.sleep(.02)
        # Core owns the close and its drain budget while the earlier control
        # is still waiting. The Server must not serialize these controls.
        assert not release.is_set() and owner.failure is None
    finally:
        release.set()
    wait_receipt(setup, closed, stages=('SUCCEEDED',))
    assert native.native.stopped
