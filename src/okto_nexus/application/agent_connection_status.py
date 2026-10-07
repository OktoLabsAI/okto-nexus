"""Dashboard connection evidence, separate from agent activity and runtime health."""
from datetime import datetime


def _fresh(value, now):
    if not value:
        return False
    try:
        age = (now - datetime.fromisoformat(value.replace('Z', '+00:00'))).total_seconds()
        return 0 <= age <= 45
    except (ValueError, TypeError):
        return False


def agent_connection_statuses(uow, now_iso):
    now = datetime.fromisoformat(now_iso.replace('Z', '+00:00'))
    rows = uow.connection.execute('''
        SELECT a.agent_id, COALESCE(p.execution_location,'local') location,
               COALESCE(o.runtime_enabled,d.runtime_enabled) runtime_enabled,
               e.executor_id,e.label,e.control_state,e.last_seen_at,
               EXISTS(SELECT 1 FROM execution_agent_recovery r WHERE r.server_id=e.server_id AND r.executor_id=e.executor_id
                      AND r.agent_id=a.agent_id AND (r.state<>'READY' OR r.generation<>e.generation)) agent_recovering,
               EXISTS(SELECT 1 FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
                   WHERE b.server_id=e.server_id AND b.executor_id=e.executor_id AND ep.agent_id=a.agent_id
                     AND ep.enabled=1 AND ep.activation_state='approved') bound,
               (EXISTS(SELECT 1 FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
                   WHERE b.server_id=e.server_id AND b.executor_id=e.executor_id AND ep.agent_id=a.agent_id
                     AND ep.activation_state='revoked') AND NOT EXISTS(
                   SELECT 1 FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
                   WHERE b.server_id=e.server_id AND b.executor_id=e.executor_id AND ep.agent_id=a.agent_id
                     AND ep.enabled=1 AND ep.activation_state='approved')) revoked,
               EXISTS(SELECT 1 FROM execution_control_lanes l
                   JOIN execution_bindings b USING(server_id,executor_id,binding_id)
                   JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
                   WHERE l.server_id=e.server_id AND l.executor_id=e.executor_id
                     AND l.agent_id=a.agent_id AND l.state='ADMITTED' AND l.expires_at>?
                     AND l.connection_generation=e.generation AND l.connection_id=e.owner_instance_id
                     AND ep.enabled=1 AND ep.activation_state='approved') admitted
        FROM agents a
        CROSS JOIN runtime_policy_defaults d
        LEFT JOIN agent_execution_policies p ON p.agent_id=a.agent_id
        LEFT JOIN agent_runtime_overrides o ON o.agent_id=a.agent_id
        LEFT JOIN execution_executors e ON e.revoked_at IS NULL AND (
          (e.kind='embedded' AND COALESCE(p.execution_location,'local')='local') OR
          (e.kind='remote' AND COALESCE(p.execution_location,'local')='remote' AND
          (e.registered_by_agent_id=a.agent_id OR EXISTS(
              SELECT 1 FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
              WHERE b.server_id=e.server_id AND b.executor_id=e.executor_id AND ep.agent_id=a.agent_id
                AND ep.enabled=1 AND ep.activation_state='approved'))))
        ORDER BY a.agent_id,e.executor_id
    ''', (now_iso,)).fetchall()
    setups = {}
    for proposal in uow.connection.execute('''
        SELECT p.subject_agent_id,p.executor_id,p.expires_at,a.status
        FROM execution_proposals p
        JOIN approvals a ON a.approval_id=json_extract(p.expected_revisions_json,'$.operator_approval_id')
        WHERE p.status='PREPARED' ORDER BY p.created_at
    '''):
        expired = datetime.fromisoformat(proposal['expires_at'].replace('Z', '+00:00')) <= now
        setups[(proposal['subject_agent_id'], proposal['executor_id'])] = (
            'Needs attention' if expired or proposal['status'] not in ('pending', 'approved') else
            'Awaiting approval' if proposal['status'] == 'pending' else 'Completing setup')
    result = {}
    for row in rows:
        item = result.setdefault(row['agent_id'], dict(
            location=row['location'], status='Offline' if row['location']=='remote' else 'Local', hosts=[]))
        if not row['runtime_enabled']:
            item['status'] = 'MCP only'
        if row['executor_id'] is None:
            continue
        if row['location'] == 'local':
            state = ('Not configured' if not row['bound'] else
                     'Recovering' if row['control_state'] == 'RECOVERING' or row['agent_recovering'] else
                     'Offline' if row['control_state'] != 'CONTROL_READY' else
                     'Ready')
            item['hosts'].append(dict(executor_id=row['executor_id'], label=row['label'] or row['executor_id'],
                                     status=state,last_seen_at=row['last_seen_at']))
            if item['status'] != 'MCP only':
                item['status'] = state
            continue
        fresh = _fresh(row['last_seen_at'], now)
        state = ('Connected' if fresh and row['control_state']=='CONTROL_READY' and row['admitted']
                 else 'Reconnecting' if fresh and row['control_state'] in ('RECOVERING','CONTROL_READY') else 'Offline')
        if row['revoked']:
            state = 'Revoked'
        if state != 'Connected' and (row['agent_id'], row['executor_id']) in setups:
            state = setups[(row['agent_id'], row['executor_id'])]
        item['hosts'].append(dict(executor_id=row['executor_id'], label=row['label'] or row['executor_id'],
                                 status=state,last_seen_at=row['last_seen_at']))
        rank = ['Offline', 'Revoked', 'Needs attention', 'Reconnecting', 'Awaiting approval', 'Completing setup', 'Connected']
        if item['status'] != 'MCP only' and rank.index(state) > rank.index(item['status']):
            item['status'] = state
    return result
