"""Bounded, scoped executor discovery for interactive selection; no native I/O."""

from ..errors import ErrorCode, OktoNexusError


def list_agent_executors(factory, *, server_id, agent_id, context, access,
                         after_executor_id=None, limit=50):
    if (not isinstance(agent_id, str) or not 1 <= len(agent_id) <= 160 or
            type(limit) is not int or not 1 <= limit <= 100 or
            (after_executor_id is not None and
             (not isinstance(after_executor_id, str) or not 1 <= len(after_executor_id) <= 160))):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid executor directory query.', {})
    with factory.unit_of_work(write=False) as uow:
        operator = access.authenticate(context, uow=uow, require_feature=False)
        if context.actor_agent_id != agent_id and not operator:
            raise OktoNexusError('SCOPE_MISMATCH', 'Only an operator may inspect another agent.', {})
        subject = access.agents.get(uow, agent_id)
        if subject is None or (not operator and not subject.is_active):
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Agent not found.', {})
        rows = uow.connection.execute(
            'SELECT e.executor_id,e.kind,e.label,e.control_state FROM execution_executors e '
            'WHERE e.server_id=? AND e.revoked_at IS NULL AND e.executor_id>? '
            "AND (? OR e.kind='embedded' OR e.registered_by_agent_id=? OR EXISTS ("
            'SELECT 1 FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id '
            'WHERE b.server_id=e.server_id AND b.executor_id=e.executor_id AND ep.agent_id=? '
            "AND ep.enabled=1 AND ep.activation_state='approved' AND ep.protocol='nxl-r4')) "
            'ORDER BY e.executor_id LIMIT ?',
            (server_id, after_executor_id or '', operator, agent_id, agent_id, limit + 1),
        ).fetchall()
        items = [dict(row) for row in rows[:limit]]
    return dict(agent_id=agent_id, items=items, has_more=len(rows) > limit,
                next_executor_id=items[-1]['executor_id'] if len(rows) > limit else None)
