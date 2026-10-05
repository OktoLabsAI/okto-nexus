"""Readiness must still hold when a delayed child is selected and sent."""
import pytest

from test_session_reuse import reuse_qualified, reuse_connected, resolve, admit
from test_local_realization import local_setup
from test_embedded_dispatch import wait_receipt
from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
from okto_nexus.errors import OktoNexusError


@pytest.mark.parametrize("boundary", ["reserve", "send"])
@pytest.mark.parametrize("stage", ["OUTCOME_UNKNOWN", "FAILED", "CANCELLED"])
def test_initial_turn_does_not_use_stale_opening_readiness(reuse_connected, boundary, stage):
    setup, binding, native = reuse_connected
    opened = resolve(setup, binding, "open", new_session=True).json()
    admit(setup, opened)
    wait_receipt(setup, opened)
    pump = setup[1].state.embedded_dispatch_owner.pump
    setup[2].portal.call(pump.stop)
    selected = resolve(setup, binding, "child", text="Delayed request").json()
    child, = admit(setup, selected, 200)["follow_up_operation_ids"]
    def reserve():
        return reserve_execution_dispatch(factory=pump.factory, server_id=pump.channel.server_id,
            executor_id=pump.channel.executor_id, remote_ready=True, channel=pump.channel)
    if boundary == "send":
        reservation = reserve()
        assert reservation.operation_id == child
    # Inject a changed durable projection while deliberately retaining stale
    # session READY. The child must check the opening fact as well.
    with pump.factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_receipts SET stage=? WHERE operation_id=?",
                               (stage, opened["operation_id"]))
    if boundary == "reserve":
        assert reserve() is None
    else:
        with pytest.raises(OktoNexusError):
            begin_execution_send(factory=pump.factory, reservation=reservation, remote_ready=True,
                fresh_publications=pump.fresh_publications, access=pump.access, channel=pump.channel)
    assert native.native.sent == []


def test_rejected_open_settles_unsent_initial_turn(reuse_connected):
    from okto_nexus.adapters.outbound.sqlite.execution_dispatch_ownership import reject_unsent_dispatch
    from okto_nexus.errors import ErrorCode
    from okto_nexus.application.execution_initial_turns import settle_failed_initial_turns
    setup, binding, native = reuse_connected
    pump = setup[1].state.embedded_dispatch_owner.pump
    setup[2].portal.call(pump.stop)
    opened = resolve(setup, binding, 'failed-parent', new_session=True, text='Never sent').json()
    child, = admit(setup, opened)['follow_up_operation_ids']
    reservation = reserve_execution_dispatch(factory=pump.factory, server_id=pump.channel.server_id,
        executor_id=pump.channel.executor_id, remote_ready=True, channel=pump.channel)
    assert reservation.operation_id == opened['operation_id']
    reject_unsent_dispatch(pump.factory, reservation=reservation,
        error=OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Authorization changed.', {}))
    with pump.factory.unit_of_work() as uow:
        # Reconciliation can repeat the cleanup without fabricating Core facts.
        settle_failed_initial_turns(uow.connection, server_id=pump.channel.server_id, executor_id=pump.channel.executor_id)
        row = uow.connection.execute('SELECT admission_state,dispatch_state,last_error FROM execution_operations '
            'JOIN execution_dispatch_outbox USING(server_id,executor_id,operation_id) WHERE operation_id=?',(child,)).fetchone()
        assert row['admission_state'] == row['dispatch_state'] == 'RESOLVED_TERMINAL'
        assert 'INITIAL_OPEN_FAILED' in row['last_error']
        assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 0
    assert native.opens == 0 and native.native.sent == []
