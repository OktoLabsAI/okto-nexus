"""Authenticated current connection facts for Connector diagnostics."""
import json
from datetime import datetime, timezone

from .agent_connection_status import _fresh
from .execution_binding_views import read_execution_binding


def connection_status(factory, *, context, access):
    now = datetime.now(timezone.utc)
    with factory.unit_of_work() as uow:
        access.authenticate(context, uow=uow, require_feature=False)
        conn = uow.connection
        rows = conn.execute('''
            SELECT b.binding_id,b.server_id,b.executor_id,e.connector_id,e.label,e.control_state,
                   e.last_seen_at,e.generation,e.owner_instance_id,ep.public_config,ep.adapter_id,ep.endpoint_id
            FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
            JOIN execution_executors e ON e.server_id=b.server_id AND e.executor_id=b.executor_id
            WHERE ep.agent_id=? AND e.kind='remote' ORDER BY b.binding_id
        ''', (context.actor_agent_id,)).fetchall()
        items = []
        for row in rows:
            binding = read_execution_binding(factory, server_id=row['server_id'], binding_id=row['binding_id'],
                context=context, access=access, uow=uow)
            admitted = conn.execute('''SELECT 1 FROM execution_control_lanes l
                JOIN execution_link_tickets t ON t.ticket_id=l.ticket_id
                WHERE l.server_id=? AND l.executor_id=? AND l.binding_id=? AND l.agent_id=?
                  AND l.state='ADMITTED' AND l.connection_generation=? AND l.connection_id=?
                  AND julianday(l.expires_at)>julianday('now') AND t.revoked_at IS NULL
                  AND julianday(t.expires_at)>julianday('now')''',
                (row['server_id'], row['executor_id'], row['binding_id'], context.actor_agent_id,
                 row['generation'], row['owner_instance_id'])).fetchone() is not None
            authorized = conn.execute('''SELECT 1 FROM runtime_execution_grants g
                JOIN agents a ON a.agent_id=g.actor_agent_id
                WHERE g.endpoint_id=? AND g.actor_agent_id=? AND g.revoked_at IS NULL
                  AND g.credential_binding=a.api_key_hash AND a.is_active=1
                  AND (g.no_expiry=1 OR julianday(g.expires_at)>julianday('now'))
                  AND (g.unlimited_actions=1 OR g.used_executions<g.max_executions) LIMIT 1''',
                (row['endpoint_id'], context.actor_agent_id)).fetchone() is not None
            online = _fresh(row['last_seen_at'], now) and row['control_state'] == 'CONTROL_READY'
            state = binding['state']
            if state == 'APPROVED':
                state = ('AUTHORIZATION_REQUIRED' if not authorized else 'CONNECTED' if online and admitted else
                         'ATTACHING' if online else 'OFFLINE')
            items.append(dict(binding_id=row['binding_id'], executor_id=row['executor_id'],
                machine_id=row['connector_id'], host=row['label'], alias=json.loads(row['public_config']).get('alias'),
                adapter_id=row['adapter_id'], status=state, approval=binding['state'],
                authorized=authorized, connected=state=='CONNECTED', last_seen_at=row['last_seen_at']))
        for row in conn.execute('''
            SELECT p.proposal_id,p.executor_id,p.proposal_json,p.expires_at,a.status,
                   e.connector_id,e.label FROM execution_proposals p
            JOIN execution_executors e ON e.server_id=p.server_id AND e.executor_id=p.executor_id
            LEFT JOIN approvals a ON a.approval_id=json_extract(p.expected_revisions_json,'$.operator_approval_id')
            WHERE p.subject_agent_id=? AND p.status='PREPARED' ORDER BY p.created_at
        ''', (context.actor_agent_id,)):
            proposal = json.loads(row['proposal_json'])
            expired = datetime.fromisoformat(row['expires_at'].replace('Z','+00:00')) <= now
            items.append(dict(proposal_id=row['proposal_id'], binding_id=proposal['binding_id'],
                executor_id=row['executor_id'], machine_id=row['connector_id'], host=row['label'],
                adapter_id=proposal['adapter_id'], connected=False,
                status='EXPIRED' if expired else 'AWAITING_APPROVAL' if row['status']=='pending' else
                       'REJECTED' if row['status'] not in ('approved',None) else 'COMPLETING_SETUP',
                approval=row['status']))
        return dict(agent_id=context.actor_agent_id, checked_at=now.isoformat(), connections=items)
