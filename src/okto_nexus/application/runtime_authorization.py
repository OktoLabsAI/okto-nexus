"""Shared runtime admission policy; P01 conservative containment.

No implicit authority for missing identities. Delegation will extend this
policy with persisted, scoped grants; it must not bypass canonical policy.
"""
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError


def authorize_runtime(context: RuntimeRequestContext, *, config, agents,
                      connection_factory, substrate: str | None = None) -> None:
    if not config.feature_harness_integrations:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                            "Harness integrations are disabled.", {})
    allowed = context.trusted_local_operator and context.authentication_source == "http_loopback"
    if context.actor_agent_id == "operator":
        with connection_factory.unit_of_work(write=False) as uow:
            actor = agents.get(uow, context.actor_agent_id)
            allowed = actor is not None and actor.is_active
    if not allowed:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                            "Runtime access requires an authorized operator or explicit delegation.", {})
    if substrate == "attach" and not config.feature_harness_attach:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                            "Claude attach requires its separate opt-in.", {})


def require_runtime_agent(*, agents, connection_factory, agent_id: str, role=None):
    with connection_factory.unit_of_work(write=False) as uow:
        agent = agents.get(uow, agent_id)
    if agent is None:
        raise OktoNexusError(ErrorCode.NOT_FOUND,
                            "Register the agent through the canonical identity API before opening a runtime.", {})
    if not agent.is_active:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime target is unavailable.", {})
    if role is not None and role != agent.role:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                            "Runtime role cannot change the canonical agent profile.", {})
    return agent
