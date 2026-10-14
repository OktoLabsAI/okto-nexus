"""Release original capacity only after fencing its pre-open owner."""
import asyncio
from typing import Protocol

from nexus_connector_core import CapacityReservation

from .capacity_admission import CapacityAdmission
from ..errors import ErrorCode, OktoNexusError


class PreopenCapacityRepository(Protocol):
    def fenced_admission(self, uow, channel, *, session_id, opening_operation_id) -> CapacityAdmission | None: ...


class ExecutionPreopenCapacity:
    def __init__(self, *, factory, repository: PreopenCapacityRepository, capacity_provider, channel):
        self.factory, self.repository = factory, repository
        self.capacity_provider, self.channel = capacity_provider, channel

    async def release(self, *, session_id, opening_operation_id):
        def read():
            with self.factory.unit_of_work(write=False) as uow:
                return self.repository.fenced_admission(uow, self.channel,
                    session_id=session_id, opening_operation_id=opening_operation_id)
        admission = await asyncio.to_thread(read)
        if admission is None:
            return
        original = admission.reservation
        capacity = await self.capacity_provider()
        observed = await capacity.release_capacity(original.request, original.reservation_id, 'SHUTDOWN')
        if (type(observed) is not CapacityReservation or observed.request != original.request
                or observed.reservation_id != original.reservation_id
                or observed.consumption != admission.consumption
                or observed.capacity_revision < original.capacity_revision or observed.state != 'RELEASED'):
            raise OktoNexusError(ErrorCode.CONFLICT, 'The original pre-open capacity is not confirmed released.', {})
        # Core's release fences delayed native admission. It does not complete
        # the handoff, undo its claim, or manufacture an execution receipt.
        # The caller must still prove empty history before retiring the session.
