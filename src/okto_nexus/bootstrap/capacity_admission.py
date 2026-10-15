"""Compose durable reservation transfer with existing handoff authorization."""
from ..application.capacity_admission import CapacityAdmissionService
from ..adapters.outbound.sqlite.capacity_admissions import SqliteCapacityAdmissionRepository
from ..adapters.inbound.mcp.tools.handoff import build_service
from ..adapters.outbound.sqlite.capacity_compensation import SqliteCapacityCompensation
from ..adapters.outbound.sqlite.execution_pending_cancellation import SqlitePendingExecutionCancellation
from .resource_pool import one_shot_pool


def build_capacity_admission(deps, *, capacity=None):
    handoffs = build_service(deps, register_approval_executor=False)
    work = handoffs.runtime_work

    def validate(uow, operation_id):
        work.revalidate(uow, operation=work.outbox.get(uow, operation_id))

    return CapacityAdmissionService(factory=deps.connection_factory,
        repository=SqliteCapacityAdmissionRepository(),
        capacity=capacity if capacity is not None else deps.runtime_availability,
        validate=validate, wake=work.wake,
        compensation=SqliteCapacityCompensation(cancellations=SqlitePendingExecutionCancellation(),
                                               pool_factory=one_shot_pool),
        recover=handoffs.recover_unconsumed_runtime_claim)
