"""Logical workspace discovery for connection setup; never disclose host paths."""
import base64
import hashlib
import json

from ..bootstrap.execution_authority import build_execution_access
from ..errors import ErrorCode, OktoNexusError
from .permissions import permission_set_for
from .connection_catalog import _object


def list_connection_workspaces(deps, context, *, limit=100, after_workspace_id=None, cursor=None, principal=None):
    if (type(limit) is not int or not 1 <= limit <= 100 or
            after_workspace_id is not None and (type(after_workspace_id) is not str
                or not 1 <= len(after_workspace_id) <= 160)):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid workspace listing cursor or limit.', {})
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        if not access.authenticate(context, uow=uow):
            permission_set_for(deps.repos.agents, uow, context.actor_agent_id).require('workspaces', 'list')
        if context.authentication_source == 'operator_session' and (type(principal) is not str or not 1 <= len(principal) <= 160):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The authenticated human identity is unavailable.', {})
        server = uow.connection.execute('SELECT server_id FROM execution_installation WHERE singleton=1').fetchone()
        if server is None:
            raise OktoNexusError(ErrorCode.CONFLICT, 'Server installation identity is unavailable.', {})
        scope = {}
        fence = hashlib.sha256(json.dumps([server[0], context.authentication_source, context.actor_agent_id,
            context.credential_binding, principal, scope], sort_keys=True).encode()).hexdigest()
        material = uow.connection.execute('SELECT COUNT(*),json_group_array(json_array(workspace_id,display_name)) '
            'FROM (SELECT workspace_id,display_name FROM workspaces ORDER BY workspace_id)').fetchone()
        revision = hashlib.sha256(material[1].encode()).hexdigest()
        if cursor is not None:
            try:
                if after_workspace_id is not None or type(cursor) is not str or not 1 <= len(cursor) <= 2048:
                    raise ValueError()
                saved = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True),
                                   object_pairs_hook=_object)
                if (set(saved) != {'kind', 'fence', 'revision', 'after', 'limit'} or saved['kind'] != 'workspaces'
                        or saved['fence'] != fence or type(saved['limit']) is not int or saved['limit'] != limit
                        or type(saved['after']) is not str or not 1 <= len(saved['after']) <= 160):
                    raise ValueError()
                if saved['revision'] != revision:
                    raise OktoNexusError(ErrorCode.CONFLICT, 'Project catalog changed; restart pagination.',
                                         {'reason': 'PROJECT_CATALOG_CHANGED'})
                after_workspace_id = saved['after']
            except (ValueError, TypeError, KeyError, UnicodeError):
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid workspace listing cursor.', {}) from None
        rows = uow.connection.execute('SELECT workspace_id,display_name FROM workspaces '
            'WHERE workspace_id>? ORDER BY workspace_id LIMIT ?', (after_workspace_id or '', limit + 1)).fetchall()
        items = [dict(r) for r in rows[:limit]]
    more = len(rows) > limit
    following = None
    if more:
        following = base64.urlsafe_b64encode(json.dumps(dict(kind='workspaces', fence=fence,
            revision=revision, after=items[-1]['workspace_id'], limit=limit), sort_keys=True).encode()).decode().rstrip('=')
    return dict(version=1, server_id=server[0], scope=scope, revision=revision, total=material[0],
                total_is_exact=True, items=items, has_more=more, next_cursor=following,
                cursor_integrity='unsigned_scope_checked', next_workspace_id=items[-1]['workspace_id'] if more else None)
