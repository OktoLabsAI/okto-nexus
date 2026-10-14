"""Transfer reserved capacity to committed execution through application ports."""
from dataclasses import dataclass
import asyncio
from typing import Protocol

from nexus_connector_core import CapacityReservation, CapacityConsumption


@dataclass(frozen=True)
class CapacityAdmission:
    operation_id: str
    reservation: CapacityReservation
    consumption: CapacityConsumption
    state: str


class CapacityAdmissionRepository(Protocol):
    def require_available(self, uow, *, handoff, endpoint_id, reservation): ...
    def attach(self, uow, *, operation_id, reservation) -> CapacityAdmission: ...
    def get(self, uow, operation_id) -> CapacityAdmission: ...
    def consumed(self, uow, admission, observed): ...
    def uncertain(self, uow, admission): ...


class CapacityAdmissionService:
    def __init__(self, *, factory, repository: CapacityAdmissionRepository, capacity, validate, wake):
        self.factory, self.repository, self.capacity = factory, repository, capacity
        self.validate, self.wake = validate, wake

    async def consume(self, operation_id):
        # No await or host I/O under the Server writer transaction.
        with self.factory.unit_of_work() as uow:
            admission = self.repository.get(uow, operation_id)
            self.validate(uow, operation_id)
            if admission.state == 'CONSUMED':
                return admission
        try:
            observed = await self.capacity.consume_capacity(admission.reservation.request,
                admission.reservation.reservation_id, admission.consumption)
            with self.factory.unit_of_work() as uow:
                self.validate(uow, operation_id)
                self.repository.consumed(uow, admission, observed)
        except (Exception, asyncio.CancelledError):
            with self.factory.unit_of_work() as uow:
                self.repository.uncertain(uow, admission)
            # The original IDs remain retained; timeout is never no-effect.
            raise
        try:
            self.wake()
        except Exception:
            pass
        with self.factory.unit_of_work(write=False) as uow:
            return self.repository.get(uow, operation_id)
