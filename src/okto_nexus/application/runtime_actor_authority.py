"""Durable provenance for messages admitted by the trusted local dashboard.

The tagged digest is not a credential and is never accepted by authentication
middleware. It can only be minted from its verified loopback request context.
Stored work rechecks the operator's identity/policy snapshot before any effect.
"""
from dataclasses import replace

from ..errors import ErrorCode, OktoNexusError

LOCAL_OPERATOR_PREFIX = "local-operator:"


def local_operator_binding(uow):
    from .execution_binding_proposals import _agent_guard
    return LOCAL_OPERATOR_PREFIX + _agent_guard(uow.connection, "operator")


def valid_actor_binding(uow, actor, binding):
    if not actor or not actor.is_active or not binding:
        return False
    if binding.startswith(LOCAL_OPERATOR_PREFIX):
        return actor.agent_id == "operator" and binding == local_operator_binding(uow)
    return bool(actor.api_key_hash and actor.api_key_hash == binding)


def authenticated_message_context(uow, context, agents):
    if context is None:
        return None
    if context.authentication_source == "http_loopback":
        if not context.trusted_local_operator or context.actor_agent_id not in (None, "operator"):
            return None
        actor = agents.get(uow, "operator")
        if not actor or not actor.is_active:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "The local operator is unavailable.", {})
        return replace(context, actor_agent_id="operator", credential_binding=local_operator_binding(uow))
    if context.authentication_source != "agent_key" or not context.credential_binding:
        return None
    actor = agents.get(uow, context.actor_agent_id)
    # A tagged provenance digest is never an agent's authentication credential.
    if (not actor or not actor.is_active or not actor.api_key_hash
            or context.credential_binding != actor.api_key_hash):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Authenticated delivery actor is unavailable.", {})
    return context
