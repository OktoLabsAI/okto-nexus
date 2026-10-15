"""Durable competition attempts, with host I/O outside the claim transaction.

Only a proved unconsumed terminal reservation (or refusal before any reserve
was sent) retires a candidate. In-flight/unknown work retains its original ID.
The repository is an application port; canonical ownership stays in handoff.
"""
import asyncio
from dataclasses import dataclass
from typing import Protocol

from nexus_connector_core import (CapacityAssessment, CapacityRequest, CapacityReservation,
                                  capacity_reservation_id)

from ..domain.handoff_automation import HandoffAutomationPrincipal
from ..errors import ErrorCode, OktoNexusError
from .handoff_automation import context_for


@dataclass(frozen=True)
class HandoffRuntimeAttempt:
    principal: HandoffAutomationPrincipal
    request: CapacityRequest
    claim_generation: int
    reservation: CapacityReservation | None
    operation_id: str | None
    state: str
    disposition: str
    reserve_started: bool
    active: bool
    reason: str | None


class HandoffRuntimeAttemptRepository(Protocol):
    def create(self, uow, *, principal, request, claim_generation) -> HandoffRuntimeAttempt: ...
    def get(self, uow, attempt_id) -> HandoffRuntimeAttempt: ...
    def reserving(self, uow, attempt_id) -> HandoffRuntimeAttempt: ...
    def unavailable(self, uow, attempt_id, reason) -> HandoffRuntimeAttempt: ...
    def observe(self, uow, attempt_id, reservation) -> HandoffRuntimeAttempt: ...
    def release_pending(self, uow, attempt_id) -> HandoffRuntimeAttempt: ...
    def uncertain(self, uow, attempt_id) -> HandoffRuntimeAttempt: ...
    def claimed(self, uow, attempt_id, operation_id) -> HandoffRuntimeAttempt: ...


class HandoffRuntimeAttemptService:
    def __init__(self, *, factory, repository: HandoffRuntimeAttemptRepository,
                 capacity, validate, claim):
        self.factory, self.repository, self.capacity = factory, repository, capacity
        self.validate, self.claim_in_transaction = validate, claim

    def prepare(self, *, principal, request, claim_generation):
        with self.factory.unit_of_work() as uow:
            self.validate(uow, principal)
            return self.repository.create(uow, principal=principal, request=request,
                                          claim_generation=claim_generation)

    def get(self, attempt_id):
        with self.factory.unit_of_work(write=False) as uow:
            return self.repository.get(uow, attempt_id)

    def _change(self, method, attempt_id, *args):
        with self.factory.unit_of_work() as uow:
            return getattr(self.repository, method)(uow, attempt_id, *args)

    async def reserve(self, attempt_id):
        attempt = self.get(attempt_id)
        if not attempt.active or attempt.operation_id:
            return attempt
        if attempt.disposition == 'RELEASE':
            return await self.release(attempt_id)
        try:
            if not attempt.reserve_started:
                assessment = await self.capacity.assess_capacity(attempt.request)
                self._assessment(attempt, assessment)
                with self.factory.unit_of_work() as uow:
                    current = self.repository.get(uow, attempt_id)
                    if not current.reserve_started and current.disposition == 'ACQUIRE' and current.active:
                        self.validate(uow, current.principal)
                        if not assessment.available:
                            return self.repository.unavailable(uow, attempt_id, assessment.reason)
                        self.repository.reserving(uow, attempt_id)
            # Always look up the original identity first, including after a
            # server restart between sending reserve and recording the reply.
            attempt = self.get(attempt_id)
            if not attempt.active or attempt.operation_id:
                return attempt
            if attempt.disposition == 'RELEASE':
                return await self.release(attempt_id)
            observed = await self.capacity.get_capacity_reservation(attempt.request)
            if observed is None:
                with self.factory.unit_of_work() as uow:
                    current = self.repository.get(uow, attempt_id)
                    if not current.active or current.operation_id or current.disposition == 'RELEASE':
                        return current
                    if current.reservation is not None:
                        raise ValueError('A known capacity reservation disappeared.')
                    self.validate(uow, current.principal)
                    self.repository.reserving(uow, attempt_id)
                observed = await self.capacity.try_reserve_capacity(attempt.request)
            if type(observed) is CapacityAssessment:
                self._assessment(attempt, observed)
                if observed.available:
                    raise ValueError('Reserve must return a reservation or a refusal.')
                # Another in-flight retry could still produce a reservation.
                # A refusal after sending is NOT a tombstone for this attempt.
                return self._change('unavailable', attempt_id, observed.reason)
            return self._change('observe', attempt_id, observed)
        except (Exception, asyncio.CancelledError):
            self._change('uncertain', attempt_id)
            raise

    @staticmethod
    def _assessment(attempt, value):
        if type(value) is not CapacityAssessment or value.request_hash != attempt.request.request_hash:
            raise ValueError('Capacity assessment does not match its durable attempt.')

    def claim(self, attempt_id):
        try:
            with self.factory.unit_of_work() as uow:
                attempt = self.repository.get(uow, attempt_id)
                if attempt.operation_id:
                    return attempt  # Replay the committed identity, never a new epoch.
                if not attempt.active or attempt.disposition != 'ACQUIRE' or attempt.state != 'RESERVED':
                    raise OktoNexusError(ErrorCode.CONFLICT, 'Attempt has no claimable reservation.', {})
                self.validate(uow, attempt.principal)
                p = attempt.principal
                result = self.claim_in_transaction(uow, workspace_id=p.workspace_id,
                    handoff_id=p.handoff_id, agent_id=p.agent_id, context=context_for(p),
                    runtime_endpoint_id=p.endpoint_id, execution_grant_id=p.grant_id,
                    idempotency_key=p.attempt_id, capacity_reservation=attempt.reservation)
                return self.repository.claimed(uow, attempt_id, result['runtime_operation']['operation_id'])
        except Exception:
            # A failed commit may be ambiguous. Re-read before scheduling any
            # cleanup, so an already committed winner cannot become a loser.
            self._change('release_pending', attempt_id)
            raise

    async def release(self, attempt_id):
        attempt = self._change('release_pending', attempt_id)
        if not attempt.active or attempt.operation_id:
            return attempt
        try:
            observed = await self.capacity.get_capacity_reservation(attempt.request)
            if observed is None:
                if attempt.reservation is not None:
                    # Lost historical storage is not proof of absent effects.
                    return self._change('uncertain', attempt_id)
                # Ask for a durable terminal record, not an empty lookup. The
                # host serializes it with reserve, fencing a delayed request.
                observed = await self.capacity.release_capacity(attempt.request,
                    capacity_reservation_id(attempt.request), 'CANCELLED')
            attempt = self._change('observe', attempt_id, observed)
            if not attempt.active or observed.state != 'HELD' or observed.consumption is not None:
                return attempt
            observed = await self.capacity.release_capacity(attempt.request, observed.reservation_id, 'LOST')
            return self._change('observe', attempt_id, observed)
        except (Exception, asyncio.CancelledError):
            self._change('uncertain', attempt_id)
            raise
