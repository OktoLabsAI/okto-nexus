"""Retired legacy opener; canonical calls use execution_compat before this boundary."""
from ..errors import ErrorCode, OktoNexusError


class RuntimeOpenService:
    def __init__(self, *, connection_factory, endpoints, agents, sessions, requests, supervisor, construct, clock, owner_guard, owner_identity=None):
        self.cf, self.endpoints, self.agents, self.sessions = connection_factory, endpoints, agents, sessions
        self.requests, self.supervisor, self.construct, self.clock = requests, supervisor, construct, clock
        self.owner_guard = owner_guard
        self.owner_identity = owner_identity

    def open(self, context, *, agent_id, kind, project_root, substrate=None, endpoint_id=None,
             target_pid=None, backend=None, role=None, metadata=None, notify_target=None, idempotency_key=None, startup_timeout_s=None):
        raise OktoNexusError(ErrorCode.CONFLICT, "Legacy connection setup was removed. Use canonical runtime integration with the agent API key.", {})
