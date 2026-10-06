"""Machine replacement is scoped to one agent and registered executor identity."""
import json
from datetime import datetime, timezone

from ..domain.base import new_id
from ..errors import ErrorCode, OktoNexusError


def other_machines(conn, *, server_id, agent_id, executor_id):
    return [dict(row) for row in conn.execute('''
        SELECT b.binding_id,b.executor_id,b.endpoint_id,b.binding_revision,
               ep.revision AS endpoint_revision,e.connector_id,e.label
        FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
        JOIN execution_executors e ON e.server_id=b.server_id AND e.executor_id=b.executor_id
        WHERE b.server_id=? AND ep.agent_id=? AND b.executor_id<>? AND e.kind='remote'
          AND e.revoked_at IS NULL AND ep.enabled=1 AND ep.activation_state='approved'
        ORDER BY b.binding_id
    ''', (server_id, agent_id, executor_id))]


def automatic_source(conn, machines, *, agent_id, adapter_id, configuration):
    if len(machines) != 1 or configuration is None:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
            'Automatic machine replacement requires one approved connection and a complete configuration.', {})
    source = conn.execute('SELECT * FROM agent_endpoints WHERE endpoint_id=?',
                          (machines[0]['endpoint_id'],)).fetchone()
    profile = conn.execute('SELECT enabled FROM runtime_profiles WHERE profile_id=?', (source['profile_id'],)).fetchone()
    if source['profile_id'] and (profile is None or not profile['enabled']):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The previous runtime profile is disabled.', {})
    public = json.loads(source['public_config'])
    from .runtime_policy import effective
    policy = effective(conn, agent_id)
    if (source['adapter_id'] != adapter_id or
            configuration['harness_settings'] != public.get('harness_settings', {}) or
            configuration['tool_access'] != public.get('nexus_tool_permission', 'ask') or
            (configuration['session_policy'] is not None and configuration['session_policy'] != policy['session_policy'])):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
            'Automatic replacement cannot change approved harness permissions or preferences. Use manual approval.', {})
    grant = conn.execute('''
        SELECT g.* FROM runtime_execution_grants g JOIN agents a ON a.agent_id=g.actor_agent_id
        WHERE g.endpoint_id=? AND g.actor_agent_id=? AND g.revoked_at IS NULL
          AND g.credential_binding=a.api_key_hash AND a.is_active=1
          AND g.no_expiry=0 AND g.unlimited_actions=0
          AND julianday(g.expires_at)>julianday('now') AND g.used_executions<g.max_executions
        ORDER BY g.created_at DESC LIMIT 1
    ''', (source['endpoint_id'], agent_id)).fetchone()
    if grant is None:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
            'The previous machine has no remaining execution authorization. Use manual approval.', {})
    return dict(endpoint_id=source['endpoint_id'], grant_id=grant['grant_id'])


def apply_machine_replacement(uow, *, expected, proposal, access, context):
    machines = expected.get('previous_machines', [])
    if not machines:
        return
    conn = uow.connection
    actual = other_machines(conn, server_id=proposal['server_id'], agent_id=proposal['agent_id'],
                            executor_id=proposal['executor_id'])
    if actual != machines:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The previously authorized machine changed after review.', {})
    now = datetime.now(timezone.utc).isoformat()
    automatic = expected.get('automatic_machine_replacement')
    if automatic:
        if access.config.remote_machine_policy != 'auto_replace':
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Automatic replacement is no longer enabled.', {})
        source = automatic_source(conn, machines, agent_id=proposal['agent_id'],
                                  adapter_id=proposal['adapter_id'], configuration=expected['connection_configuration'])
        if source != automatic:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The source execution authorization changed.', {})
        endpoint = conn.execute('SELECT public_config,response_policy FROM agent_endpoints WHERE endpoint_id=?',
                                (source['endpoint_id'],)).fetchone()
        public = json.loads(endpoint['public_config'])
        public['alias'] = expected['alias']
        conn.execute('UPDATE agent_endpoints SET public_config=?,response_policy=? WHERE endpoint_id=?',
                     (json.dumps(public), endpoint['response_policy'], proposal['endpoint_id']))
        grant = dict(conn.execute('SELECT * FROM runtime_execution_grants WHERE grant_id=?', (source['grant_id'],)).fetchone())
        grant.update(grant_id=new_id('grant'), endpoint_id=proposal['endpoint_id'],
                     workspace_id=proposal['workspace_id'], revision=1, profile_revision=1 if proposal['profile_id'] else None)
        # Carry the original expiry AND consumption; reconnecting never refills a budget.
        columns = tuple(grant)
        conn.execute(f"INSERT INTO runtime_execution_grants({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                     tuple(grant.values()))
    for machine in machines:
        endpoint_id, binding_id = machine['endpoint_id'], machine['binding_id']
        from .execution_revocation import invalidate_sessions
        invalidate_sessions(conn, endpoint_id=endpoint_id, now=now)
        conn.execute("UPDATE agent_endpoints SET enabled=0,activation_state='revoked',revision=revision+1,updated_at=? WHERE endpoint_id=?", (now, endpoint_id))
        conn.execute('UPDATE runtime_execution_grants SET revoked_at=?,revision=revision+1 WHERE endpoint_id=? AND revoked_at IS NULL', (now, endpoint_id))
        conn.execute('UPDATE execution_link_tickets SET revoked_at=? WHERE server_id=? AND binding_id=? AND revoked_at IS NULL', (now, proposal['server_id'], binding_id))
        conn.execute("UPDATE execution_control_lanes SET state='DISCONNECTED' WHERE server_id=? AND binding_id=?", (proposal['server_id'], binding_id))
        conn.execute('UPDATE execution_session_capabilities SET revoked_at=? WHERE server_id=? AND executor_id=? '
                     'AND session_id IN (SELECT session_id FROM execution_sessions WHERE server_id=? AND executor_id=? AND binding_id=?) '
                     'AND revoked_at IS NULL', (now, proposal['server_id'], machine['executor_id'], proposal['server_id'], machine['executor_id'], binding_id))
        access.endpoints.audit_configuration(uow, context=context, kind='remote_machine', resource_id=endpoint_id,
            old_revision=machine['endpoint_revision'], new_revision=machine['endpoint_revision']+1,
            fields=['revoke_previous_machine', 'automatic_policy' if automatic else 'operator_approval'], now=now)
