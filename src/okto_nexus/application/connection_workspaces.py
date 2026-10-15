"""Logical workspace discovery for connection setup; never disclose host paths."""
from ..bootstrap.execution_authority import build_execution_access
from ..errors import ErrorCode, OktoNexusError
from .permissions import permission_set_for


def list_connection_workspaces(deps, context, *, limit=100, after_workspace_id=None):
    if (type(limit) is not int or not 1 <= limit <= 100 or
            after_workspace_id is not None and (type(after_workspace_id) is not str
                or not 1 <= len(after_workspace_id) <= 160)):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid workspace listing cursor or limit.', {})
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        if not access.authenticate(context, uow=uow):
            permission_set_for(deps.repos.agents, uow, context.actor_agent_id).require('workspaces', 'list')
        rows = uow.connection.execute('SELECT workspace_id,display_name FROM workspaces '
            'WHERE workspace_id>? ORDER BY workspace_id LIMIT ?', (after_workspace_id or '', limit + 1)).fetchall()
        items = [dict(r) for r in rows[:limit]]
    more = len(rows) > limit
    return dict(items=items, has_more=more, next_workspace_id=items[-1]['workspace_id'] if more else None)
