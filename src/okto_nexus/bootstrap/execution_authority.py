"""Transport-neutral composition of canonical policy for R4 authority."""

from ..adapters.outbound.sqlite.endpoints_repo import SqliteEndpointRepo
from ..adapters.outbound.sqlite.runtime_grants_repo import SqliteRuntimeGrantRepo
from ..application.runtime_access import RuntimeAccessService


def build_execution_access(deps):
    # Remote technical availability comes from the executor's Core inventory.
    # This service evaluates canonical identity, endpoint, grant and policy;
    # it must not discover or launch the remote provider on the Server.
    return RuntimeAccessService(
        connection_factory=deps.connection_factory, agents=deps.repos.agents,
        endpoints=SqliteEndpointRepo(), grants=SqliteRuntimeGrantRepo(),
        config=deps.config, clock=deps.clock)


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
    capabilities = ExecutionCapabilityService(factory=deps.connection_factory,
                                               access=build_execution_access(deps))
    return NativeActionService(factory=deps.connection_factory, capabilities=capabilities,
        repository=SqliteNativeActionRepository(), clock=deps.clock,
        build_handoff=lambda factory: build_service(
            ExecutionToolDependencies(deps, factory), register_approval_executor=False))
