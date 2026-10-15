"""Capture already-authorized creator context and recheck approved requests."""
import json

from ..domain.execution_principal import current_execution_principal, current_execution_tool
from ..domain.handoff_origin import HandoffOrigin
from ..errors import ErrorCode, OktoNexusError
from .message_session_origin import runtime_key


PREFIX = 'handoff-creator-v1:'


def managed_creator(uow, *, capabilities, agent_id, workspace_id):
    principal = current_execution_principal.get()
    if principal is None:
        return None
    if (capabilities is None or principal.audience != 'nexus-mcp-session'
            or current_execution_tool.get() != 'handoff_create'
            or principal.scope['agent_id'] != agent_id or principal.scope['workspace_id'] != workspace_id):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The handoff creator is outside its managed session.', {})
    from .execution_binding_proposals import _agent_guard
    reference = capabilities.principal_reference(uow, principal=principal, actions=('tools/call', 'handoff_create'))
    binding = PREFIX + json.dumps({'principal': reference, 'agent_guard': _agent_guard(uow.connection, agent_id)},
                                   sort_keys=True, separators=(',', ':'))
    return binding, HandoffOrigin(runtime_key(principal.scope))


def valid_approved_creator(uow, *, actor, binding, origin, capabilities, workspace_id):
    if not actor or not actor.is_active or not binding:
        return False
    if not binding.startswith(PREFIX):
        return bool(actor.api_key_hash and actor.api_key_hash == binding)
    if capabilities is None:
        return False
    from .execution_binding_proposals import _agent_guard
    try:
        proof = json.loads(binding[len(PREFIX):])
        if set(proof) != {'principal', 'agent_guard'} or proof['principal']['audience'] != 'nexus-mcp-session':
            return False
        reference = capabilities.authorize_recorded_principal(uow, reference=proof['principal'],
                                                               actions=('tools/call', 'handoff_create'))
        return (reference['scope']['agent_id'] == actor.agent_id
                and reference['scope']['workspace_id'] == workspace_id
                and origin.source_session_key == runtime_key(reference['scope'])
                and proof['agent_guard'] == _agent_guard(uow.connection, actor.agent_id))
    except (KeyError, TypeError, ValueError, OktoNexusError):
        return False
