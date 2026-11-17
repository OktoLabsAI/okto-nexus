"""Read-only, operator-authorized project proofs on the Server's own host."""
import json
from pathlib import Path

from ..bootstrap.execution_authority import build_execution_access
from ..errors import ErrorCode, OktoNexusError
from .connection_setup import require_operator
from .execution_local_realizations import _digest, directory_identity


def project_context_in(uow, *, executor_id, project_root=None, workspace_id=None, include_private_identity=False):
    conn = uow.connection
    installation = conn.execute('SELECT server_id FROM execution_installation WHERE singleton=1').fetchone()
    executor = conn.execute('SELECT * FROM execution_executors WHERE executor_id=? AND server_id=?',
                            (executor_id, installation[0] if installation else '')).fetchone()
    if installation is None or executor is None or executor['server_id'] != installation[0]:
        raise OktoNexusError(ErrorCode.NOT_FOUND, 'Execution host not found on this Server.', {})
    workspace = None
    if workspace_id is not None:
        workspace = conn.execute('SELECT workspace_id,display_name FROM workspaces WHERE workspace_id=?',
                                 (workspace_id,)).fetchone()
        if workspace is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Workspace not found.', {})
    if project_root is not None and executor['kind'] != 'embedded':
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                             'A remote folder must be approved on its own execution host.', {})
    if executor['revoked_at'] is not None:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The execution host has been revoked.', {})
    if project_root is not None:
        local_id = conn.execute('SELECT embedded_executor_id FROM execution_installation WHERE singleton=1').fetchone()[0]
        if executor_id != local_id:
            raise OktoNexusError(ErrorCode.CONFLICT, 'This directory is not on the selected execution host.', {})
    identity = directory_identity(project_root) if project_root is not None else None
    if identity is None and workspace_id is None:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Select a project or an approved local directory.', {})
    rows = [] if executor['kind'] != 'embedded' else conn.execute(
        'SELECT l.local_record_json,r.realization_ref,r.workspace_binding_id,w.workspace_id,'
        'p.display_name,w.revision AS mapping_revision,r.revision AS realization_revision '
        'FROM execution_local_realizations l '
        'JOIN execution_realizations r ON r.server_id=l.server_id AND r.executor_id=l.executor_id '
        'AND r.realization_ref=l.realization_ref '
        'JOIN execution_workspace_bindings w ON w.server_id=r.server_id AND w.executor_id=r.executor_id '
        'AND w.workspace_binding_id=r.workspace_binding_id '
        'JOIN workspaces p ON p.workspace_id=w.workspace_id '
        "WHERE l.server_id=? AND l.executor_id=? AND r.status='READY' AND w.status='READY' "
        'ORDER BY w.workspace_id,r.workspace_binding_id,r.realization_ref '
        'LIMIT 10001', (installation[0], executor_id)).fetchall()
    if len(rows) > 10000:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The authorized project mapping inventory is incomplete.',
                             {'reason': 'PROJECT_INVENTORY_INCOMPLETE'})
    mappings, matching, proof_rows = {}, set(), []
    for row in rows:
        try:
            root = json.loads(row['local_record_json'])['root']
            if (type(root) is not dict or set(root) != {'path', 'device', 'inode'}
                    or type(root['path']) is not str or not 1 <= len(root['path']) <= 4096
                    or '\x00' in root['path'] or not Path(root['path']).is_absolute()
                    or any(type(root[key]) is not str or not root[key].isascii() or not root[key].isdecimal()
                           for key in ('device', 'inode'))):
                raise ValueError()
        except (ValueError, TypeError, KeyError, RecursionError):
            raise OktoNexusError(ErrorCode.CONFLICT, 'The authorized project mapping inventory is incomplete.',
                                 {'reason': 'PROJECT_INVENTORY_INCOMPLETE'}) from None
        same = identity is not None and root == identity
        if same:
            matching.add(row['workspace_id'])
        if same or row['workspace_id'] == workspace_id:
            material = [row['workspace_id'], row['workspace_binding_id'], row['realization_ref'],
                        row['mapping_revision'], row['realization_revision'], root]
            revision = _digest(material)
            proof_rows.append(material)
            key = (row['workspace_id'], row['workspace_binding_id'], root['path'])
            mappings[key] = dict(workspace_id=row['workspace_id'], label=row['display_name'],
                                 workspace_root=root['path'], workspace_binding_id=row['workspace_binding_id'],
                                 revision=revision)
    proof = [installation[0], executor_id, executor['kind'], workspace_id,
             dict(workspace) if workspace is not None else None, identity, proof_rows]
    association = 'new_project' if workspace_id is None else (
        'existing_mapping' if workspace_id in matching else 'new_mapping')
    result = dict(version=1, server_id=installation[0], executor_id=executor_id, workspace_id=workspace_id,
                project_root=identity['path'] if identity else None, project_revision=_digest(proof),
                mapped_workspace_ids=sorted(matching), association=association,
                mappings=list(mappings.values()))
    if include_private_identity:
        result['_directory_identity'] = identity
    return result


def read_project_context(deps, context, *, executor_id, project_root=None, workspace_id=None):
    if project_root is not None and (type(project_root) is not str or not 1 <= len(project_root) <= 4096
                                     or '\x00' in project_root):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid project directory.', {})
    for value in (executor_id, workspace_id):
        if value is not None and (type(value) is not str or not 1 <= len(value) <= 160 or not value.isprintable()):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid project scope.', {})
    with deps.connection_factory.unit_of_work(write=False) as uow:
        require_operator(build_execution_access(deps), context, uow)
        return project_context_in(uow, executor_id=executor_id, project_root=project_root, workspace_id=workspace_id)
