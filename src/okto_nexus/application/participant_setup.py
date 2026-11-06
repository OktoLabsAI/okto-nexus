"""Read-only preparation of an existing identity's external MCP client."""
from dataclasses import asdict

from ..domain.permissions import PermissionSet, PERMISSION_REGISTRY
from ..errors import ErrorCode, OktoNexusError
from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from .connection_policy import require_method
from .execution_local_realizations import _digest
from .runtime_policy import effective


def participant_context(deps, agent_id, workspace_id):
    if agent_id == 'operator':
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
            'A human operator credential cannot configure an external participant.', {})
    if not isinstance(workspace_id, str) or not 1 <= len(workspace_id) <= 160:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Select an existing workspace ID.', {})
    with deps.connection_factory.unit_of_work(write=False) as uow:
        server_id, revisions, projection = current_agent_revisions(deps.connection_factory,
            agent_id=agent_id, uow=uow, persist=False)
        require_method(uow, agent_id, 'mcp')
        workspace = uow.connection.execute('SELECT workspace_id,display_name FROM workspaces WHERE workspace_id=?',
            (workspace_id,)).fetchone()
        if workspace is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'The selected workspace is unavailable. Select an existing workspace; no workspace was created.', {})
        perms = PermissionSet(projection['permissions'])
        result = dict(participant_setup_revision=1, server_id=server_id, agent_id=agent_id,
            display_name=projection['metadata'].get('display_name', agent_id), workspace=dict(workspace),
            permissions=sorted(f'{group}.{flag}' for group, values in PERMISSION_REGISTRY.items()
                if group != 'limits' for flag in values if perms.allows(group, flag)),
            revisions=asdict(revisions), runtime_enabled=effective(uow.connection, agent_id)['runtime_enabled'],
            delivery='One logical delivery per identity; another client is not guaranteed to consume each message.',
            mcp_enabled=True)
        # Read-only revision projections may remain old+1 across multiple
        # unpersisted changes. Bind approval to the actual current policy/key,
        # without disclosing their raw rows or advancing execution revisions.
        identity = dict(uow.connection.execute(
            'SELECT permissions,comm_scope,api_key_hash,is_active FROM agents WHERE agent_id=?',
            (agent_id,)).fetchone())
        methods = [dict(row) for row in uow.connection.execute(
            'SELECT method,enabled FROM agent_connection_methods WHERE agent_id=? ORDER BY method', (agent_id,))]
        return result | dict(review_revision=_digest(dict(context=result, identity=identity, methods=methods)))
