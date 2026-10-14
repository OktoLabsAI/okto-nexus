"""Transfer reserved capacity to committed execution through application ports."""
from dataclasses import dataclass
import asyncio
from typing import Protocol

from nexus_connector_core import CapacityReservation, CapacityConsumption
from ..errors import ErrorCode, OktoNexusError


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
    def cancelled_no_effect(self, uow, admission, observed): ...
    def compensated_claim(self, uow, operation_id): ...
    def unsent_release_pending(self, uow, admission) -> bool: ...
    def released_after_unsent_refusal(self, uow, admission, observed): ...


class CapacityAdmissionCompensation(Protocol):
    def cancel(self, uow, admission):
        """Fence the original operations and retire their logical admission."""
        ...


class CapacityAdmissionService:
    def __init__(self, *, factory, repository: CapacityAdmissionRepository, capacity, validate, wake,
                 compensation: CapacityAdmissionCompensation, recover):
        self.factory, self.repository, self.capacity = factory, repository, capacity
        self.validate, self.wake = validate, wake
        self.compensation, self.recover = compensation, recover

    async def consume(self, operation_id):
        # No await or host I/O under the Server writer transaction.
        with self.factory.unit_of_work() as uow:
            admission = self.repository.get(uow, operation_id)
            release_pending = self.repository.unsent_release_pending(uow, admission)
            if admission.state in {'CONSUMED', 'CANCELLED_NO_EFFECT'}:
                return admission
        try:
            if release_pending:
                # A committed Server refusal fenced the send. Core still owns
                # the physical gate and must confirm release; neither a timeout
                # nor the business handoff status can stand in for that proof.
                released = await self.capacity.release_capacity(admission.reservation.request,
                    admission.reservation.reservation_id, 'REVOKED')
                with self.factory.unit_of_work() as uow:
                    self.repository.released_after_unsent_refusal(uow, admission, released)
                    return self.repository.get(uow, operation_id)
            # Query the original ticket even if productive authority changed.
            # Missing history or a timeout never proves absence of consumption.
            observed = await self.capacity.get_capacity_reservation(admission.reservation.request)
            if (type(observed) is not CapacityReservation
                    or observed.request != admission.reservation.request
                    or observed.reservation_id != admission.reservation.reservation_id
                    or observed.capacity_revision < admission.reservation.capacity_revision):
                raise ValueError('Original capacity reservation could not be confirmed.')
            if self._terminal_ticket(observed):
                return self._compensate(admission, observed)
            try:
                with self.factory.unit_of_work() as uow:
                    self.validate(uow, operation_id)
            except OktoNexusError as error:
                return await self._retire_invalid(admission, observed, error)
            observed = await self.capacity.consume_capacity(admission.reservation.request,
                admission.reservation.reservation_id, admission.consumption)
            if self._terminal_ticket(observed):
                return self._compensate(admission, observed)
            try:
                with self.factory.unit_of_work() as uow:
                    self.validate(uow, operation_id)
                    self.repository.consumed(uow, admission, observed)
            except OktoNexusError as error:
                return await self._retire_invalid(admission, observed, error)
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

    @staticmethod
    def _terminal_ticket(observed):
        return (type(observed) is CapacityReservation
            and observed.state in {'EXPIRED_UNCONSUMED', 'RELEASED'})

    async def _retire_invalid(self, admission, observed, error):
        if (error.code != ErrorCode.PERMISSION_DENIED or type(observed) is not CapacityReservation
                or observed.request != admission.reservation.request
                or observed.reservation_id != admission.reservation.reservation_id
                or observed.consumption not in (None, admission.consumption)):
            raise error
        # Revocation/decision can race consumption without native dispatch.
        # Core releases only an unused gate, otherwise retains RELEASE_PENDING.
        # A RELEASED ticket still needs exact local unsent-operation proof.
        released = await self.capacity.release_capacity(admission.reservation.request,
            admission.reservation.reservation_id, 'REVOKED')
        if self._terminal_ticket(released):
            return self._compensate(admission, released)
        raise error

    def _compensate(self, admission, observed):
        with self.factory.unit_of_work() as uow:
            current = self.repository.get(uow, admission.operation_id)
            if current.state == 'CANCELLED_NO_EFFECT':
                return current
            self.repository.cancelled_no_effect(uow, admission, observed)
            self.compensation.cancel(uow, admission)
            self.recover(uow, admission.operation_id)
            result = self.repository.get(uow, admission.operation_id)
        try:
            self.wake()
        except Exception:
            pass
        return result
