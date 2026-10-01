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
