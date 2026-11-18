"""Recover the exact capacity claim over the existing Core capacity port."""

from functools import partial

import anyio
from nexus_connector_core import CapacityReservation

from ..adapters.outbound.sqlite.session_interaction import (
    confirm_dispatch_capacity,
    mark_dispatch_capacity_uncertain,
    read_dispatch_capacity,
    retire_unconsumed_dispatch,
)
from ..errors import ErrorCode, OktoNexusError


async def consume_input_capacity(*, factory, scope, operation_id, capacity) -> CapacityReservation:
    """Observe or consume a single already-staged claim. Release the R4 hold on proof."""
    key = {'scope': scope, 'operation_id': operation_id}

    def read():
        with factory.unit_of_work(write=False) as uow:
            return read_dispatch_capacity(uow, **key)

    def apply(function, **options):
        with factory.unit_of_work() as uow:
            return function(uow, **key, **options)

    claim = await anyio.to_thread.run_sync(read)
    if claim.state in ('CONSUMED', 'CANCELLED_NO_EFFECT'):
        return claim.reservation
    if claim.state not in ('WAITING_CONSUMPTION', 'NEEDS_RECONCILIATION'):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The capacity claim is no longer awaiting consumption.', {})
    try:
        expected = claim.reservation
        observed = await capacity.get_capacity_reservation(expected.request)
        if (type(observed) is not CapacityReservation or observed.request != expected.request
                or observed.reservation_id != expected.reservation_id):
            raise OktoNexusError(ErrorCode.CONFLICT, 'The original host capacity claim could not be confirmed.', {})
        if observed.state == 'HELD':
            observed = await capacity.consume_capacity(expected.request, expected.reservation_id, claim.consumption)
        reconcile = (retire_unconsumed_dispatch if type(observed) is CapacityReservation and observed.state in (
            'RELEASED', 'EXPIRED_UNCONSUMED') else confirm_dispatch_capacity)
        await anyio.to_thread.run_sync(partial(apply, reconcile, observed=observed))
    except Exception:
        await anyio.to_thread.run_sync(partial(apply, mark_dispatch_capacity_uncertain))
        raise
    return observed
