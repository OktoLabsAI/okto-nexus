"""Read-only session directory for operator conversations, not agent inventory."""
from dataclasses import replace

from ..bootstrap.execution_authority import build_execution_access
from ..errors import ErrorCode, OktoNexusError
from .agent_runtime_administration import require_operator
from .execution_session_views import read_execution_session


def conversation_sessions(deps, context, *, workspace=None, agent=None, page=1):
    if type(page) is not int or not 1 <= page <= 100000:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid session page.', {})
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        require_operator(access, context, uow)
        if not context.actor_agent_id:
            context = replace(context, actor_agent_id='operator')
        # Both runtime.start and turn.submit may reference one logical delivery.
        # Preserve retry history, deduplicate sessions and count messages once.
        source = '''WITH links AS (
            SELECT server_id,executor_id,operation_id,domain_operation_id FROM execution_domain_deliveries
            UNION
            SELECT server_id,executor_id,operation_id,domain_operation_id FROM execution_delivery_attempt_history
        ), interactions AS (
            SELECT o.server_id,o.executor_id,o.session_id,m.message_id,m.created_at,m.subject
            FROM links l JOIN execution_operations o USING(server_id,executor_id,operation_id)
            JOIN delivery_outbox d ON d.operation_id=l.domain_operation_id
            JOIN messages m ON m.message_id=d.message_id
            WHERE m.from_agent_id='operator'
        ), conversations AS (
            SELECT server_id,executor_id,session_id,MAX(created_at) AS last_interaction_at,
                   COUNT(DISTINCT message_id) AS interaction_count
            FROM interactions GROUP BY server_id,executor_id,session_id
        ) '''
        joins = ''' FROM conversations c JOIN execution_sessions s USING(server_id,executor_id,session_id)
            JOIN execution_bindings b USING(server_id,executor_id,binding_id)
            JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
            JOIN execution_executors e USING(server_id,executor_id)
            WHERE (? IS NULL OR s.workspace_id=?) AND (? IS NULL OR ep.agent_id=?)'''
        args = (workspace, workspace, agent, agent)
        opened = "(s.lifecycle_state<>'CLOSED' AND NOT (s.lifecycle_state='FAILED' AND s.lease_state IN ('NONE','CLOSED')))"
        conn = uow.connection
        counts = conn.execute(source + 'SELECT COUNT(*),COALESCE(SUM(' + opened + '),0)' + joins, args).fetchone()
        rows = conn.execute(source + '''SELECT s.server_id,s.executor_id,s.session_id,ep.agent_id,ep.adapter_id,
            e.kind,e.label,c.last_interaction_at,c.interaction_count,''' + opened + ''' AS is_open,
            (SELECT i.subject FROM interactions i WHERE i.server_id=s.server_id AND i.executor_id=s.executor_id
                AND i.session_id=s.session_id ORDER BY i.created_at DESC,i.message_id DESC LIMIT 1) AS subject
            ''' + joins + ' ORDER BY is_open DESC,c.last_interaction_at DESC,s.rowid DESC LIMIT 20 OFFSET ?',
            (*args, (page - 1) * 20)).fetchall()
        items = []
        for row in rows:
            session = read_execution_session(deps.connection_factory, server_id=row['server_id'],
                executor_id=row['executor_id'], session_id=row['session_id'], context=context, access=access, _uow=uow)
            items.append(session | dict(harness=row['adapter_id'], location=row['kind'],
                host=row['label'] or ('Nexus server' if row['kind']=='embedded' else row['executor_id']),
                last_interaction_at=row['last_interaction_at'], interaction_count=row['interaction_count'],
                subject=row['subject'], is_open=bool(row['is_open'])))
        return dict(items=items, total=counts[0], active_count=counts[1], page=page, has_more=page * 20 < counts[0])
