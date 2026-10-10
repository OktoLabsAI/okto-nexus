"""Operator view of live instances and the ten most recently finished turns."""
from dataclasses import replace

from ..errors import ErrorCode, OktoNexusError
from ..bootstrap.execution_authority import build_execution_access
from .execution_session_views import read_execution_session


def require_operator(access, context, uow):
    # Polling is read-only. Maintenance authorization also inserts an audit
    # record and must not run inside a deferred read transaction.
    if not access.authenticate(context, uow=uow, require_feature=False):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Runtime administration requires an operator.', {})


def overview(deps, context, agent_id, *, after=0):
    if type(after) is not int or after < 0:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid instance cursor.', {})
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        require_operator(access, context, uow)
        if access.agents.get(uow, agent_id) is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Agent does not exist.', {})
        if not context.actor_agent_id:
            context = replace(context, actor_agent_id='operator')
        conn = uow.connection
        configured = conn.execute('SELECT 1 FROM execution_bindings b JOIN agent_endpoints ep '
            'ON ep.endpoint_id=b.endpoint_id WHERE ep.agent_id=? LIMIT 1', (agent_id,)).fetchone()
        if not configured:
            raise OktoNexusError(ErrorCode.CONFLICT, 'This agent has no runtime integration.', {})
        source = (' FROM execution_sessions s JOIN execution_bindings b USING(server_id,executor_id,binding_id) '
            'JOIN execution_executors e USING(server_id,executor_id) '
            'JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id '
            "WHERE ep.agent_id=? AND s.lifecycle_state<>'CLOSED' "
            "AND NOT (s.lifecycle_state='FAILED' AND s.lease_state='CLOSED') ")
        total = conn.execute('SELECT COUNT(*)' + source, (agent_id,)).fetchone()[0]
        rows = conn.execute('SELECT s.rowid AS cursor,s.server_id,s.executor_id,s.session_id,e.label,e.kind,ep.adapter_id' +
            source + 'AND s.rowid>? ORDER BY s.rowid LIMIT 51', (agent_id, after)).fetchall()
        active = []
        for row in rows[:50]:
            session = read_execution_session(deps.connection_factory, server_id=row['server_id'],
                executor_id=row['executor_id'], session_id=row['session_id'], context=context, access=access, _uow=uow)
            pool = conn.execute('SELECT state FROM one_shot_slots WHERE executor_id=? AND session_id=? '
                'AND agent_id=? LIMIT 1', (row['executor_id'], row['session_id'], agent_id)).fetchone()
            active.append(session | dict(host=row['label'] or ('Nexus server' if row['kind']=='embedded' else row['executor_id']),
                location=row['kind'], harness=row['adapter_id'], pool_state=pool[0] if pool else None))
        # Sort by completion, not opening time or session ID. A shared session
        # can contribute several completed calls while remaining active.
        completed = conn.execute('''
            SELECT o.operation_id,o.server_id,o.executor_id,o.session_id,o.binding_id,o.workspace_id,
                   o.created_at,r.received_at AS completed_at,r.stage AS outcome,ep.adapter_id AS harness,
                   COALESCE(e.label,CASE WHEN e.kind='embedded' THEN 'Nexus server' ELSE e.executor_id END) AS host
            FROM execution_operations o JOIN execution_receipts r USING(server_id,executor_id,operation_id)
            JOIN execution_bindings b USING(server_id,executor_id,binding_id)
            JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
            JOIN execution_executors e USING(server_id,executor_id)
            WHERE o.subject_agent_id=? AND o.action IN ('turn.submit','turn.steer')
              AND r.stage IN ('SUCCEEDED','FAILED','CANCELLED')
              AND r.receipt_revision=(SELECT MAX(last.receipt_revision) FROM execution_receipts last
                  WHERE last.server_id=o.server_id AND last.executor_id=o.executor_id AND last.operation_id=o.operation_id)
            ORDER BY r.received_at DESC,o.operation_id DESC LIMIT 10
        ''', (agent_id,)).fetchall()
        return dict(agent_id=agent_id, active=active, active_count=total, has_more=len(rows)>50,
                    next_after=rows[49]['cursor'] if len(rows)>50 else after,
                    completed=[dict(row) for row in completed])


def execution(deps, context, agent_id, operation_id, executor_id):
    from ..adapters.outbound.sqlite.execution_receipts import read_execution_operation_history
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        require_operator(access, context, uow)
        installation = uow.connection.execute('SELECT server_id FROM execution_installation WHERE singleton=1').fetchone()
        if installation is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Runtime installation was not found.', {})
        server_id = installation['server_id']
    return read_execution_operation_history(deps.connection_factory,
        server_id=server_id,
        executor_id=executor_id, operation_id=operation_id, subject_agent_id=agent_id).public_view()
