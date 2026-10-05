"""Durable provenance for messages admitted by the trusted local dashboard.

The tagged digest is not a credential and is never accepted by authentication
middleware. It can only be minted from its verified loopback request context.
Stored work rechecks the operator's identity/policy snapshot before any effect.
"""
from dataclasses import replace
import json

from nexus_connector_core.protocol import canonical_json

from ..errors import ErrorCode, OktoNexusError

LOCAL_OPERATOR_PREFIX = "local-operator:"
MANAGED_MESSAGE_PREFIX = "managed-message-v1:"


def managed_message_binding(uow, *, capabilities, actor_id, workspace_id):
    """Capture verified session authority, never a credential copied from an agent.

    The reference is internal provenance. Replaying it as an inbound credential
    cannot authenticate a caller; deferred effects recheck the live capability.
    """
    from ..domain.execution_principal import current_execution_principal, current_execution_tool
    from .execution_binding_proposals import _agent_guard
    principal = current_execution_principal.get()
    if principal is None:
        return None
    action = 'message_create' if principal.audience == 'nexus-mcp-session' else 'message.create'
    if (capabilities is None or principal.audience not in {'nexus-mcp-session', 'nexus-native-session'}
            or current_execution_tool.get() != action
            or principal.scope['agent_id'] != actor_id or principal.scope['workspace_id'] != workspace_id):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Message sender is outside its runtime session scope.', {})
    actions = ('tools/call', action) if principal.audience == 'nexus-mcp-session' else (action,)
    reference = capabilities.principal_reference(uow, principal=principal, actions=actions)
    return MANAGED_MESSAGE_PREFIX + canonical_json({
        'principal': reference, 'agent_guard': _agent_guard(uow.connection, actor_id)}).decode()


def local_operator_binding(uow):
    from .execution_binding_proposals import _agent_guard
    return LOCAL_OPERATOR_PREFIX + _agent_guard(uow.connection, "operator")


def valid_actor_binding(uow, actor, binding, *, capabilities=None, workspace_id=None):
    if not actor or not actor.is_active or not binding:
        return False
    if binding.startswith(LOCAL_OPERATOR_PREFIX):
        return actor.agent_id == "operator" and binding == local_operator_binding(uow)
    if binding.startswith(MANAGED_MESSAGE_PREFIX):
        if capabilities is None or workspace_id is None:
            return False
        from .execution_binding_proposals import _agent_guard
        try:
            proof = json.loads(binding[len(MANAGED_MESSAGE_PREFIX):])
            if set(proof) != {'principal', 'agent_guard'}:
                return False
            audience = proof['principal']['audience']
            if audience not in {'nexus-mcp-session', 'nexus-native-session'}:
                return False
            actions = ('tools/call', 'message_create') if audience == 'nexus-mcp-session' else ('message.create',)
            reference = capabilities.authorize_recorded_principal(uow, reference=proof['principal'], actions=actions)
            return (reference['scope']['agent_id'] == actor.agent_id
                    and reference['scope']['workspace_id'] == workspace_id
                    and proof['agent_guard'] == _agent_guard(uow.connection, actor.agent_id))
        except (KeyError, TypeError, ValueError, OktoNexusError):
            return False
    return bool(actor.api_key_hash and actor.api_key_hash == binding)


def authenticated_message_context(uow, context, agents, *, capabilities=None, workspace_id=None):
    if context is None:
        return None
    if context.authentication_source == 'session_capability':
        actor = agents.get(uow, context.actor_agent_id)
        if not valid_actor_binding(uow, actor, context.credential_binding,
                                   capabilities=capabilities, workspace_id=workspace_id):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Runtime message authority is no longer valid.', {})
        return context
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
