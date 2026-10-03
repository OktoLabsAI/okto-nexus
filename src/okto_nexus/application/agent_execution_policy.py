"""Agent execution restrictions; workspace selection belongs to work, not identity.

Policy revisions participate in the proposal/intent source guard. They invalidate
unsubmitted and undispatched work without changing an existing lease's identity:
that lease may still authorize containment. RuntimeAccess rechecks this policy
for every new effect and lease issuance rechecks the source guard.
"""
from nexus_connector_core import get_runtime_catalog
from ..errors import ErrorCode, OktoNexusError


def policy_view(uow, agent_id):
    row = uow.connection.execute('SELECT * FROM agent_execution_policies WHERE agent_id=?', (agent_id,)).fetchone()
    return dict(row) if row else dict(agent_id=agent_id, execution_location='all', local_adapter_id=None, revision=0)


def require_execution_location(uow, *, agent_id, executor_id, adapter_id):
    from .runtime_policy import effective
    if not effective(uow.connection, agent_id)['runtime_enabled']:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Runtime is disabled; this agent uses MCP only.', {'reason': 'RUNTIME_DISABLED'})
    row = uow.connection.execute('SELECT e.kind FROM execution_executors e JOIN execution_installation i '
        'ON i.server_id=e.server_id AND i.singleton=1 WHERE e.executor_id=? LIMIT 2', (executor_id,)).fetchall()
    if len(row) != 1:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Execution host is not uniquely identified.', {})
    local = row[0]['kind'] == 'embedded'
    policy = policy_view(uow, agent_id)
    if policy['execution_location'] not in ('all', 'local' if local else 'remote'):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Execution host is restricted by the agent policy.', {'reason': 'EXECUTION_LOCATION_RESTRICTED'})
    if local and policy['local_adapter_id'] is not None and policy['local_adapter_id'] != adapter_id:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Local runtime integration is restricted by the agent policy.', {'reason': 'LOCAL_INTEGRATION_RESTRICTED'})


def read_policy(deps, context, agent_id):
    from ..bootstrap.execution_authority import build_execution_access
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        operator = access.authenticate(context, uow=uow, require_feature=False)
        if not operator and context.actor_agent_id != agent_id:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Agent execution policy is outside this identity.', {})
        if access.agents.get(uow, agent_id) is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Agent does not exist.', {})
        result = policy_view(uow, agent_id)
    result['local_integrations'] = [dict(adapter_id=r.adapter_id, label=r.display_name) for r in get_runtime_catalog().runtimes
                                    if r.support_status == 'managed_supported']
    return result


def save_policy(deps, context, agent_id, *, expected_revision, execution_location, local_adapter_id):
    from ..bootstrap.execution_authority import build_execution_access
    access = build_execution_access(deps)
    catalog = {r.adapter_id for r in get_runtime_catalog().runtimes if r.support_status == 'managed_supported'}
    if (type(expected_revision) is not int or expected_revision < 0 or execution_location not in ('local','remote','all')
            or local_adapter_id is not None and local_adapter_id not in catalog):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid agent execution policy.', {})
    with deps.connection_factory.unit_of_work() as uow:
        access.authorize_maintenance(context, uow=uow)
        if access.agents.get(uow, agent_id) is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Agent does not exist.', {})
        current = policy_view(uow, agent_id)
        if current['revision'] != expected_revision:
            raise OktoNexusError(ErrorCode.CONFLICT, 'Execution policy changed; reload before saving.', {})
        if execution_location != 'remote' and local_adapter_id is None:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Select the local runtime integration before saving Local or All.', {})
        uow.connection.execute('INSERT INTO agent_execution_policies VALUES(?,?,?,?) ON CONFLICT(agent_id) DO UPDATE SET '
            'execution_location=excluded.execution_location,local_adapter_id=excluded.local_adapter_id,revision=excluded.revision',
            (agent_id, execution_location, local_adapter_id, expected_revision + 1))
        access.endpoints.audit_configuration(uow, context=context, kind='agent_execution_policy', resource_id=agent_id,
            old_revision=expected_revision, new_revision=expected_revision+1, fields=['execution_location','local_adapter_id'], now=deps.clock.now_iso())
    return read_policy(deps, context, agent_id)
