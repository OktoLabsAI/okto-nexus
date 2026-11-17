"""One scoped relation for catalog fingerprint, exact total and keyset page."""
from ..harness.event_journal import redact

_RELATION = """
SELECT b.server_id,b.binding_id,b.executor_id,b.endpoint_id,b.workspace_binding_id,
 e.agent_id,e.workspace_id,e.adapter_id,b.binding_revision,b.realization_revision,
 e.revision AS endpoint_revision,e.activation_state,e.enabled AS endpoint_enabled,
 a.is_active AS agent_active,(x.revoked_at IS NOT NULL) AS executor_revoked,
 CASE WHEN x.kind='remote' THEN 'remote' ELSE 'local' END AS execution_location,
 substr(COALESCE(CASE WHEN json_valid(a.metadata) THEN CASE WHEN json_type(a.metadata,'$.display_name')='text' THEN json_extract(a.metadata,'$.display_name') END END,a.agent_id),1,120) AS agent_label,
 substr(COALESCE(w.display_name,e.workspace_id),1,120) AS workspace_label,
 substr(COALESCE(x.label,x.executor_id),1,120) AS host_label,
 public.connect_id,public.revision AS public_connection_revision
FROM execution_bindings b JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id
JOIN agents a ON a.agent_id=e.agent_id
JOIN execution_executors x ON x.server_id=b.server_id AND x.executor_id=b.executor_id
LEFT JOIN workspaces w ON w.workspace_id=e.workspace_id
LEFT JOIN connection_public_ids public INDEXED BY connection_public_id_binding
 ON public.server_id=b.server_id AND public.state='bound'
 AND public.canonical_ref_json IS NOT NULL
 AND public.adapter_id=e.adapter_id
 AND public.workspace_id=e.workspace_id
 AND json_extract(public.canonical_ref_json,'$.server_id')=b.server_id
 AND json_extract(public.canonical_ref_json,'$.executor_id')=b.executor_id
 AND json_extract(public.canonical_ref_json,'$.binding_id')=b.binding_id
 AND json_extract(public.canonical_ref_json,'$.endpoint_id')=b.endpoint_id
 AND json_extract(public.canonical_ref_json,'$.workspace_binding_id')=b.workspace_binding_id
 AND json_extract(public.canonical_ref_json,'$.agent_id')=e.agent_id
 AND json_extract(public.canonical_ref_json,'$.workspace_id')=e.workspace_id
WHERE b.server_id=?
"""
_FIELDS = ('server_id', 'binding_id', 'executor_id', 'endpoint_id', 'workspace_binding_id',
    'agent_id', 'workspace_id', 'adapter_id', 'binding_revision', 'realization_revision',
    'endpoint_revision', 'activation_state', 'endpoint_enabled', 'agent_active', 'executor_revoked',
    'execution_location', 'agent_label', 'workspace_label', 'host_label', 'connect_id', 'public_connection_revision')


class SqliteConnectionCatalogQueries:
    def read(self, uow, *, server_id, scope, after, limit):
        relation, arguments = _RELATION, [server_id]
        for field in ('workspace_id', 'agent_id', 'executor_id'):
            if field in scope:
                relation += ' AND ' + ('b.' if field == 'executor_id' else 'e.') + field + '=?'
                arguments.append(scope[field])
        if 'execution_location' in scope:
            relation += " AND (CASE WHEN x.kind='remote' THEN 'remote' ELSE 'local' END)=?"
            arguments.append(scope['execution_location'])
        ordered = relation + ' ORDER BY b.executor_id,b.binding_id'
        # Hash only bounded public projection fields; no config blob, folder,
        # grant/key material, transcript, filesystem or inventory probe.
        summary = uow.connection.execute('SELECT COUNT(*),json_group_array(json_array('
            + ','.join(_FIELDS) + ')) FROM (' + ordered + ')', arguments).fetchone()
        rows = [dict(row) for row in uow.connection.execute('SELECT * FROM (' + relation + ') '
            'WHERE executor_id>? OR (executor_id=? AND binding_id>?) '
            'ORDER BY executor_id,binding_id LIMIT ?', [*arguments, after[0], after[0], after[1], limit + 1])]
        for row in rows:
            for key in ('agent_label', 'workspace_label', 'host_label'):
                row[key] = ' '.join(redact(row[key]).split())[:120]
            for key in ('endpoint_enabled', 'agent_active', 'executor_revoked'):
                row[key] = bool(row[key])
            row['needs_revalidation'] = True
        return summary[0], summary[1], rows
