"""Caller and deferred-dispatch authority for native question responses."""
import json

from nexus_connector_core.protocol import canonical_json

from ..domain.execution_principal import current_execution_principal, current_execution_tool
from ..errors import ErrorCode, OktoNexusError
from .execution_binding_proposals import _agent_guard
from .execution_capabilities import ExecutionCapabilityService


MANAGED_INPUT_PREFIX = 'managed-input-v1:'


def input_authority(uow, *, factory, access, context, action, workspace_id=None, recorded_guard=None):
    """Return actor, durable guard and workspace ceiling, without agent-key impersonation.

    recorded_guard is internal: only a committed Server decision may supply it.
    It cannot authenticate an inbound request and is never accepted from tools.
    """
    def deny():
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The native question caller is outside its session scope.', {})

    if context is None or action not in {'runtime_input_list', 'runtime_input_respond'}:
        deny()
    actor = context.actor_agent_id or 'operator'
    principal = current_execution_principal.get()
    recorded = recorded_guard is not None and recorded_guard.startswith(MANAGED_INPUT_PREFIX)
    if principal is None and not recorded:
        access.authenticate(context, uow=uow, require_feature=False)
        guard = _agent_guard(uow.connection, actor)
        if recorded_guard is not None and guard != recorded_guard:
            deny()
        return actor, guard, workspace_id

    capabilities = ExecutionCapabilityService(factory=factory, access=access)
    proof = None
    if recorded:
        try:
            proof = json.loads(recorded_guard[len(MANAGED_INPUT_PREFIX):])
            if set(proof) != {'agent_guard', 'principal'}:
                deny()
            audience = proof['principal']['audience']
        except (ValueError, KeyError, TypeError):
            deny()
    else:
        audience = principal.audience
    native_action = {'runtime_input_list': 'runtime.input.list', 'runtime_input_respond': 'runtime.input.respond'}[action]
    actions = ('tools/call', action) if audience == 'nexus-mcp-session' else (native_action,)
    if audience not in {'nexus-mcp-session', 'nexus-native-session'}:
        deny()
    if recorded:
        reference = capabilities.authorize_recorded_principal(uow, reference=proof['principal'], actions=actions)
    else:
        if current_execution_tool.get() != (action if audience == 'nexus-mcp-session' else native_action):
            deny()
        reference = capabilities.principal_reference(uow, principal=principal, actions=actions)
    scope = reference['scope']
    if scope['agent_id'] != actor or (workspace_id is not None and scope['workspace_id'] != workspace_id):
        deny()
    guard = _agent_guard(uow.connection, actor)
    if proof is not None and proof['agent_guard'] != guard:
        deny()
    if proof is None:
        proof = {'agent_guard': guard, 'principal': reference}
    return actor, MANAGED_INPUT_PREFIX + canonical_json(proof).decode(), scope['workspace_id']
