"""Compose attempt orchestration with the shared claim and authorization kernels."""
from ..adapters.inbound.mcp.tools.handoff import build_service
from ..adapters.outbound.sqlite.handoff_runtime_attempts import SqliteHandoffRuntimeAttemptRepository
from ..application.handoff_runtime_attempts import HandoffRuntimeAttemptService
from ..application.handoff_automation import context_for


def build_handoff_runtime_attempts(deps, *, capacity=None):
    handoffs = build_service(deps, register_approval_executor=False)

    def validate(uow, principal):
        handoffs.runtime_work.access.authorize(context_for(principal), action='execute_work',
            endpoint_id=principal.endpoint_id, represented_agent_id=principal.agent_id,
            workspace_id=principal.workspace_id, uow=uow, audit=False)

    return HandoffRuntimeAttemptService(factory=deps.connection_factory,
        repository=SqliteHandoffRuntimeAttemptRepository(),
        capacity=capacity if capacity is not None else deps.runtime_availability,
        validate=validate, claim=handoffs.claim_managed_in_transaction)
