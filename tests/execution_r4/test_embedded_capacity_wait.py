"""An ordinary canonical turn waits behind a reservation, with controls live."""
import asyncio
import time

from test_capacity_authority import request
from test_embedded_dispatch import connected_local, local_setup, admit, wait_receipt


def test_wait_keeps_original_operation_and_allows_control_and_lease_renewal(connected_local):
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    owner = app.state.embedded_dispatch_owner
    owner.host.capacity_enabled = True
    owner.leases.max_duration_ms = 4000
    opened = admit(setup, binding, 'wait-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    req = request(setup, binding, scope=opened['scope'], unit='next_turn')
    async def reserve():
        service = await owner.execution_capacity()
        return await service.try_reserve_capacity(req)
    held = client.portal.call(reserve)
    assert held.state == 'HELD'
    try:
        waiting = admit(setup, binding, 'wait-turn', 'turn.submit',
                        session_id=opened['session_id'], text='Wait for reserved capacity')
        deadline = time.monotonic() + 15
        while True:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                flow = uow.connection.execute('SELECT state FROM execution_capacity_waits WHERE operation_id=?',
                                              (waiting['operation_id'],)).fetchone()
            if flow is not None and flow['state'] == 'WAITING':
                break
            assert not owner.agents.blocked and owner.failure is None
            assert time.monotonic() < deadline
            time.sleep(.01)
        assert not native.native.sent
        interrupted = admit(setup, binding, 'wait-interrupt', 'turn.interrupt', session_id=opened['session_id'],
                            target={'kind': 'current_run', 'expected_turn_id': None})
        wait_receipt(setup, interrupted)
        client.portal.call(owner._renew_owned, opened['session_id'], owner.sessions[opened['session_id']])
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT MAX(lease_serial) FROM execution_leases WHERE session_id=?',
                                           (opened['session_id'],)).fetchone()[0] >= 2
            assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts WHERE operation_id=?',
                                           (waiting['operation_id'],)).fetchone()[0] == 0
            assert uow.connection.execute('SELECT dispatch_state,attempt_no FROM execution_dispatch_outbox WHERE operation_id=?',
                                           (waiting['operation_id'],)).fetchone()[:] == ('SENDING', 1)
    finally:
        async def release():
            service = await owner.execution_capacity()
            return await service.release_capacity(req, held.reservation_id, 'LOST')
        client.portal.call(release)
    wait_receipt(setup, waiting)
    assert native.native.sent == [('interrupt', interrupted['operation_id']), ('send_turn', waiting['operation_id'])]
    assert owner.failure is None and not owner.agents.blocked
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT attempt_no FROM execution_dispatch_outbox WHERE operation_id=?',
                                       (waiting['operation_id'],)).fetchone()[0] == 1
