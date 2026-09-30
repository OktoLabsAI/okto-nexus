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
