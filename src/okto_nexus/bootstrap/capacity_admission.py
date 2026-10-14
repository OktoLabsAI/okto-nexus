"""Compose durable reservation transfer with existing handoff authorization."""
from ..application.capacity_admission import CapacityAdmissionService
from ..adapters.outbound.sqlite.capacity_admissions import SqliteCapacityAdmissionRepository
from ..adapters.inbound.mcp.tools.handoff import build_service


def build_capacity_admission(deps, *, capacity=None):
    work = build_service(deps, register_approval_executor=False).runtime_work

    def validate(uow, operation_id):
        work.revalidate(uow, operation=work.outbox.get(uow, operation_id))

    return CapacityAdmissionService(factory=deps.connection_factory,
        repository=SqliteCapacityAdmissionRepository(),
        capacity=capacity if capacity is not None else deps.runtime_availability,
        validate=validate, wake=work.wake)
