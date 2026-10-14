"""Transport-neutral composition of canonical policy for R4 authority."""

from ..adapters.outbound.sqlite.endpoints_repo import SqliteEndpointRepo
from ..adapters.outbound.sqlite.runtime_grants_repo import SqliteRuntimeGrantRepo
from ..adapters.outbound.sqlite.execution_tool_claims import SqliteExecutionClaimRepository
from ..application.runtime_access import RuntimeAccessService


def build_message_capabilities(deps):
    from ..application.execution_capabilities import ExecutionCapabilityService
    return ExecutionCapabilityService(factory=deps.connection_factory, access=build_execution_access(deps))


def build_execution_access(deps):
    # Remote technical availability comes from the executor's Core inventory.
    # This service evaluates canonical identity, endpoint, grant and policy;
    # it must not discover or launch the remote provider on the Server.
    access = RuntimeAccessService(
        connection_factory=deps.connection_factory, agents=deps.repos.agents,
        endpoints=SqliteEndpointRepo(), grants=SqliteRuntimeGrantRepo(),
        config=deps.config, clock=deps.clock,
        admission_fence=deps.runtime_admission_fence)
    def validate_delivery(uow, operation):
        from ..adapters.inbound.mcp.tools.messages import build_service
        from ..application.runtime_delivery import RuntimeDeliveryPlanner
        from ..adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
        from ..errors import ErrorCode, OktoNexusError
        if (operation["status"] in {"REJECTED", "CANCELLED", "FAILED_FINAL"}
                or operation["canonical_terminal_operation_id"] is not None
                or uow.connection.execute('SELECT 1 FROM execution_delivery_releases WHERE domain_operation_id=?',
                    (operation['operation_id'],)).fetchone() is not None
                or uow.connection.execute("SELECT 1 FROM message_deliveries WHERE delivery_id=? "
                    "AND consumer_kind='push' AND consumer_operation_id=? AND status='unread'",
                    (operation["delivery_id"], operation["operation_id"])).fetchone() is None):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "The delivery no longer owns its logical claim.", {})
        planner = RuntimeDeliveryPlanner(endpoints=access.endpoints, outbox=SqliteRuntimeOutboxRepo(),
            agents=access.agents, registry=None, config=deps.config, capabilities=build_message_capabilities(deps))
        if uow.connection.execute("SELECT 1 FROM runtime_handoff_bindings WHERE operation_id=?", (operation["operation_id"],)).fetchone():
            from ..adapters.inbound.mcp.tools.handoff import build_service as build_handoff
            build_handoff(deps, register_approval_executor=False).runtime_work.revalidate(uow, operation=operation)
            planner.causality.validate_dispatch(uow, operation=operation, now=deps.clock.now_iso())
            return
        planner.revalidate(uow, operation=operation, config=deps.config)
        messages = build_service(deps)
        messages.revalidate_runtime_delivery(uow, operation)
        if operation.get("source_result_id"):
            messages._runtime_results.validate_relay(uow, operation["source_result_id"])
        planner.causality.validate_dispatch(uow, operation=operation, now=deps.clock.now_iso())
    access.validate_domain_delivery = validate_delivery
    access.execution_claims = SqliteExecutionClaimRepository()
    from ..application.execution_work_leases import ExecutionWorkLeaseAuthority
    from ..adapters.outbound.sqlite.execution_work_leases import SqliteRunningHandoffRepository
    def validate_running_work(uow, operation):
        from ..adapters.inbound.mcp.tools.handoff import build_service as build_handoff
        build_handoff(deps, register_approval_executor=False).runtime_work.revalidate(uow, operation=operation)
    access.work_lease_authority = ExecutionWorkLeaseAuthority(
        repository=SqliteRunningHandoffRepository(), validate=validate_running_work)
    from ..application.execution_session_containment import ExecutionSessionContainment
    from ..adapters.outbound.sqlite.execution_session_containment import SqliteSessionContainmentRepository
    access.session_containment = ExecutionSessionContainment(factory=deps.connection_factory,
        repository=SqliteSessionContainmentRepository(), clock=deps.clock)
    from ..application.execution_session_release import ExecutionSessionRelease
    from ..adapters.outbound.sqlite.execution_session_release import SqliteSessionReleaseRepository
    def project_release(uow, channel, session_id, proof):
        from ..application.execution_domain_delivery import project_released_deliveries
        project_released_deliveries(uow.connection, server_id=channel.server_id,
            executor_id=channel.executor_id, session_id=session_id, proof=proof)
    access.session_release = ExecutionSessionRelease(factory=deps.connection_factory,
        repository=SqliteSessionReleaseRepository(), containment=access.session_containment, project=project_release)
    return access


class ExecutionToolDependencies:
    """Keep shared services/live owners while decorating the tool transaction port."""

    def __init__(self, deps, factory):
        object.__setattr__(self, '_deps', deps)
        object.__setattr__(self, 'connection_factory', factory)

    def __getattr__(self, name):
        return getattr(self._deps, name)

    def __setattr__(self, name, value):
        setattr(self._deps, name, value)


def build_native_action_service(deps):
    """One canonical composition for native HTTP and the embedded Core caller."""
    from ..application.execution_capabilities import ExecutionCapabilityService
    from ..application.execution_native_actions import NativeActionService
    from ..adapters.outbound.sqlite.execution_native_actions import SqliteNativeActionRepository
    from ..adapters.inbound.mcp.tools.handoff import build_service
    from ..adapters.inbound.mcp.tools.messages import build_service as build_messages
    from ..adapters.inbound.mcp.tools.identity import build_service as build_identity
    from ..adapters.inbound.mcp.tools.health import build_service as build_health
    capabilities = ExecutionCapabilityService(factory=deps.connection_factory,
                                               access=build_execution_access(deps))
    return NativeActionService(factory=deps.connection_factory, capabilities=capabilities,
        repository=SqliteNativeActionRepository(), clock=deps.clock,
        native_decisions=deps.native_decisions,
        build_identity=lambda factory: build_identity(ExecutionToolDependencies(deps, factory)),
        build_health=lambda factory: build_health(ExecutionToolDependencies(deps, factory)),
        build_messages=lambda factory: build_messages(
            ExecutionToolDependencies(deps, factory), register_approval_executor=False),
        build_handoff=lambda factory: build_service(
            ExecutionToolDependencies(deps, factory), register_approval_executor=False))
