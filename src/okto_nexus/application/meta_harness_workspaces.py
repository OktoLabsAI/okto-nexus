"""Namespaces offered by the selected agent's current connection configuration."""
from .connection_policy import method_enabled
from .runtime_policy import effective
from ..errors import ErrorCode, OktoNexusError


def recipient_workspaces(uow, agent_id, *, runtime_available=True):
    conn = uow.connection
    policy = conn.execute('SELECT execution_location FROM agent_execution_policies WHERE agent_id=?', (agent_id,)).fetchone()
    location = policy[0] if policy else 'local'
    configured = conn.execute("SELECT 1 FROM agent_endpoints WHERE agent_id=? AND protocol='nxl-r4' LIMIT 1", (agent_id,)).fetchone()
    runtime = bool(runtime_available and configured and effective(conn, agent_id)['runtime_enabled'])
    if runtime:
        rows = conn.execute('''
            SELECT DISTINCT ep.workspace_id,ep.adapter_id
            FROM agent_endpoints ep
            JOIN runtime_profiles p ON p.profile_id=ep.profile_id
            JOIN execution_bindings b ON b.endpoint_id=ep.endpoint_id
            JOIN execution_executors x USING(server_id,executor_id)
            WHERE ep.agent_id=? AND ep.enabled=1 AND ep.activation_state='approved'
              AND ep.protocol='nxl-r4' AND p.enabled=1 AND x.revoked_at IS NULL
              AND x.kind=? AND ep.consumption='exclusive' AND ep.response_policy='conversation'
        ''', (agent_id, 'remote' if location == 'remote' else 'embedded'))
        ids = {r['workspace_id'] for r in rows if method_enabled(uow, agent_id, r['adapter_id'])}
    else:
        ids = {r[0] for r in conn.execute('SELECT DISTINCT workspace_id FROM sessions WHERE agent_id=? AND closed_at IS NULL', (agent_id,))}
    items = [dict(r) for r in conn.execute('SELECT workspace_id,display_name FROM workspaces ORDER BY display_name,workspace_id') if r['workspace_id'] in ids]
    return dict(agent_id=agent_id, runtime=runtime, items=items)


def validate_recipient_workspace(uow, agent_id, workspace_id, *, runtime_available=True):
    result = recipient_workspaces(uow, agent_id, runtime_available=runtime_available)
    # MCP inbox semantics remain unchanged; runtime execution needs an approved
    # binding in the exact namespace, never an implicit cross-namespace fallback.
    if result['runtime'] and workspace_id not in {r['workspace_id'] for r in result['items']}:
        raise OktoNexusError(ErrorCode.CONFLICT,
            'The selected agent has no approved runtime connection in this namespace. Select one of its available namespaces.',
            {'reason': 'AGENT_WORKSPACE_MISMATCH', 'agent_id': agent_id,
             'available_workspaces': result['items']})
