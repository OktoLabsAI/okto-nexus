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
        LEFT JOIN execution_executors e ON e.kind='remote' AND e.revoked_at IS NULL
          AND (e.registered_by_agent_id=a.agent_id OR EXISTS(
              SELECT 1 FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
              WHERE b.server_id=e.server_id AND b.executor_id=e.executor_id AND ep.agent_id=a.agent_id
                AND ep.enabled=1 AND ep.activation_state='approved'))
        ORDER BY a.agent_id,e.executor_id
    ''', (now_iso,)).fetchall()
    result = {}
    for row in rows:
        item = result.setdefault(row['agent_id'], dict(
            location=row['location'], status='Offline' if row['location']=='remote' else 'Local', hosts=[]))
        if not row['runtime_enabled']:
            item['status'] = 'MCP only'
        if row['executor_id'] is None or row['location'] != 'remote':
            continue
        fresh = _fresh(row['last_seen_at'], now)
        state = ('Connected' if fresh and row['control_state']=='CONTROL_READY' and row['admitted']
                 else 'Reconnecting' if fresh and row['control_state'] in ('RECOVERING','CONTROL_READY') else 'Offline')
        item['hosts'].append(dict(executor_id=row['executor_id'], label=row['label'] or row['executor_id'],
                                 status=state,last_seen_at=row['last_seen_at']))
        if item['status'] != 'MCP only' and ['Offline','Reconnecting','Connected'].index(state) > ['Offline','Reconnecting','Connected'].index(item['status']):
            item['status'] = state
    return result
