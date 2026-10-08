"""Managed tool admission and transaction-bound authority checks.

The reviewed surface grows as domain paths acquire workspace/session guards.
Unadapted global inbox and credential/admin tools never inherit an agent key.
"""

from contextlib import contextmanager

from ..domain.execution_principal import current_execution_principal, current_execution_tool
from ..domain.ids import resolve_workspace_id as resolve_path_workspace_id
from ..errors import ErrorCode, OktoNexusError


MANAGED_TOOLS = frozenset({
    'agent_whoami', 'agent_list', 'agent_get', 'capability_list', 'coordination_health',
    'handoff_list_available', 'handoff_get',
    'handoff_claim', 'handoff_complete',
    'event_get', 'event_cursor', 'event_wait',
    'runtime_input_list', 'runtime_input_respond',
    'message_create',
})


def denied(message='The tool is outside this session capability scope.'):
    return OktoNexusError(ErrorCode.PERMISSION_DENIED, message, {})


def resolve_tool_workspace(project_root):
    principal = current_execution_principal.get()
    if principal is None:
        return resolve_path_workspace_id(project_root)
    # Managed callers use the approved canonical handle. Never resolve a path
    # supplied by a remote executor against the Server filesystem.
    expected = principal.scope['workspace_id']
    if project_root != expected:
        raise denied('Use the workspace ID bound to this managed session.')
    return expected


def check_tool_arguments(name, arguments):
    principal = current_execution_principal.get()
    if principal is None:
        return
    if name == 'harness_list':
        raise denied('Session capabilities cannot administer runtime connections. '
                     'Use agent_list or agent_get for reachable agent status.')
    if principal.audience != 'nexus-mcp-session' or name not in MANAGED_TOOLS:
        raise denied('This tool does not support session capabilities yet.')
    for field, target in (('agent_id', 'agent_id'), ('from_agent_id', 'agent_id'),
                          ('session_id', 'session_id'), ('workspace_id', 'workspace_id')):
        # agent_get names a discovery target, never the authenticated caller.
        # IdentityService applies the caller's outbound and target's inbound scope.
        if name == 'agent_get' and field == 'agent_id':
            continue
        if arguments.get(field) is not None and arguments[field] != principal.scope[target]:
            raise denied()
    if arguments.get('project_root') is not None:
        resolve_tool_workspace(arguments['project_root'])
    if arguments.get('session_secret') is not None:
        raise denied('A managed session uses its capability, not a separate session secret.')
    if name == 'message_create' and arguments.get('from_session_id') is not None:
        raise denied('The managed sender session is supplied by the authenticated capability.')
    if any(arguments.get(k) is not None for k in (
            'runtime_endpoint_id', 'execution_grant_id', 'idempotency_key')):
        raise denied('A managed tool call cannot request another runtime execution.')


NATIVE_ACTIONS = {
    'agent_list': 'agent.list', 'agent_get': 'agent.get',
    'capability_list': 'capability.list', 'coordination_health': 'coordination.health',
    'message_create': 'message.create',
    'input_list': 'runtime.input.list', 'input_respond': 'runtime.input.respond',
    'context': 'handoff.get', 'claim': 'handoff.claim', 'complete': 'handoff.complete',
}


def execution_actions(principal):
    action = current_execution_tool.get()
    if principal.audience == 'nexus-mcp-session' and action in MANAGED_TOOLS:
        return ('tools/call', action)
    if principal.audience == 'nexus-native-session' and action in NATIVE_ACTIONS.values():
        return (action,)
    raise denied()


class ExecutionToolConnectionFactory:
    """Decorate the existing unit-of-work port for managed MCP services only.

    Authorization runs after BEGIN, including after a writer-lock wait, in
    the transaction that reads or changes domain state. Long polls repeat it
    on each read. Canonical key callers keep their existing behavior.
    """

    def __init__(self, inner, capabilities):
        self.inner, self.capabilities = inner, capabilities

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @contextmanager
    def unit_of_work(self, write=True):
        with self.inner.unit_of_work(write=write) as uow:
            principal = current_execution_principal.get()
            if principal is not None:
                self.capabilities.authorize_principal(uow, principal=principal,
                    actions=execution_actions(principal))
            yield uow


class BoundExecutionConnectionFactory(ExecutionToolConnectionFactory):
    """Join one native request transaction; never commit a nested domain call.

    A fresh instance belongs to one synchronous invocation, never to shared
    application state. The outer factory retains commit/rollback ownership.
    """

    def __init__(self, inner, capabilities, uow):
        super().__init__(inner, capabilities)
        self._uow = uow

    @contextmanager
    def unit_of_work(self, write=True):
        principal = current_execution_principal.get()
        if principal is None:
            raise denied()
        self.capabilities.authorize_principal(self._uow, principal=principal,
                                              actions=execution_actions(principal))
        yield self._uow
