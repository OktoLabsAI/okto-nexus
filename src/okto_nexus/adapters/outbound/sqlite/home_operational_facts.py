"""Bounded batch proof reads for negotiated Home, with no host calls."""
import json

from ....application.execution_native_facts import effective_lease_facts
from ....domain.home_entries import SessionRuntimeFact
from ..harness.event_journal import redact

SESSIONS = '''
WITH opening AS (
 SELECT r.*,ROW_NUMBER() OVER(PARTITION BY r.server_id,r.executor_id,r.operation_id
 ORDER BY r.receipt_revision DESC) AS position
 FROM execution_receipts r JOIN execution_operations o USING(server_id,executor_id,operation_id)
 WHERE o.server_id=:server_id AND o.action='runtime.open'
 AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
), closing AS (
 SELECT DISTINCT server_id,executor_id,session_id FROM execution_operations
 WHERE server_id=:server_id AND (:workspace_id IS NULL OR workspace_id=:workspace_id)
 AND action='runtime.close' AND admission_state NOT IN ('REJECTED','RESOLVED_TERMINAL')
), observed AS (
 SELECT o.server_id,o.executor_id,o.session_id,MAX(r.received_at) AS observed_at
 FROM execution_operations o JOIN execution_receipts r USING(server_id,executor_id,operation_id)
 WHERE o.server_id=:server_id AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
 GROUP BY o.server_id,o.executor_id,o.session_id
)
SELECT s.*,o.subject_agent_id AS agent_id,o.expected_revisions_json,
 e.control_state,e.generation,e.owner_instance_id,e.revoked_at,
 ep.enabled,ep.activation_state,ep.health,a.is_active,
 b.binding_revision,b.workspace_binding_id AS current_wxb,r.status AS realization_status,
 r.revision AS current_realization_revision,b.realization_revision,
 r.workspace_binding_id AS realization_workspace_binding_id,
 ar.authorization_revision AS current_authorization_revision,
 ar.configuration_revision AS current_configuration_revision,ar.credential_epoch AS current_credential_epoch,
 w.status AS workspace_status,p.display_name AS workspace_label,v.observed_at,
 opened.stage AS opening_stage,opened.native_id AS opening_native_id,
 closing.session_id AS closing_session_id,
 COALESCE(wm.gap_state,'none') AS gap_state,
 COALESCE(wm.projected_through,0) AS projected_through,COALESCE(wm.committed_contiguous,0) AS committed_contiguous,
 COALESCE(policy.session_policy,defaults.session_policy) AS session_policy,
 CASE WHEN recovery.agent_id IS NOT NULL AND (recovery.state<>'READY' OR recovery.generation<>e.generation)
 THEN 1 ELSE 0 END AS recovering
FROM execution_sessions s
JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id
 AND o.operation_id=s.open_operation_id AND o.action='runtime.open' AND o.session_id=s.session_id
 AND o.binding_id=s.binding_id AND o.workspace_binding_id=s.workspace_binding_id AND o.workspace_id=s.workspace_id
JOIN execution_executors e ON e.server_id=s.server_id AND e.executor_id=s.executor_id
LEFT JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id AND b.binding_id=s.binding_id
LEFT JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id AND ep.agent_id=o.subject_agent_id AND ep.workspace_id=s.workspace_id
LEFT JOIN agents a ON a.agent_id=o.subject_agent_id
LEFT JOIN execution_agent_revisions ar ON ar.server_id=s.server_id AND ar.agent_id=o.subject_agent_id
LEFT JOIN execution_realizations r ON r.server_id=b.server_id AND r.executor_id=b.executor_id AND r.realization_ref=b.realization_ref
LEFT JOIN execution_workspace_bindings w ON w.server_id=s.server_id AND w.executor_id=s.executor_id
 AND w.workspace_binding_id=s.workspace_binding_id AND w.workspace_id=s.workspace_id
LEFT JOIN workspaces p ON p.workspace_id=s.workspace_id
LEFT JOIN execution_agent_recovery recovery ON recovery.server_id=s.server_id
 AND recovery.executor_id=s.executor_id AND recovery.agent_id=o.subject_agent_id
LEFT JOIN observed v ON v.server_id=s.server_id AND v.executor_id=s.executor_id AND v.session_id=s.session_id
LEFT JOIN opening opened ON opened.server_id=s.server_id AND opened.executor_id=s.executor_id
 AND opened.operation_id=s.open_operation_id AND opened.position=1
LEFT JOIN agent_runtime_overrides policy ON policy.agent_id=o.subject_agent_id
LEFT JOIN runtime_policy_defaults defaults ON defaults.singleton=1
LEFT JOIN closing ON closing.server_id=s.server_id AND closing.executor_id=s.executor_id AND closing.session_id=s.session_id
LEFT JOIN execution_event_watermarks wm ON wm.server_id=s.server_id AND wm.executor_id=s.executor_id
 AND wm.session_id=s.session_id AND wm.stream_epoch=s.stream_epoch
WHERE s.server_id=:server_id AND (:workspace_id IS NULL OR s.workspace_id=:workspace_id)
'''

LEASES = '''
WITH ranked AS (
 SELECT l.*,ROW_NUMBER() OVER(PARTITION BY l.server_id,l.executor_id,l.session_id ORDER BY l.lease_serial DESC) AS position
 FROM execution_leases l JOIN execution_sessions s USING(server_id,executor_id,session_id)
 WHERE s.server_id=:server_id AND (:workspace_id IS NULL OR s.workspace_id=:workspace_id)
) SELECT * FROM ranked WHERE position<=2
'''


def normalize(rows, leases, check_budget):
    by_session = {}
    for lease in leases:
        check_budget()
        key = tuple(lease[n] for n in ('server_id', 'executor_id', 'session_id'))
        by_session.setdefault(key, {})[lease['position']] = lease
    result = []
    for row in rows:
        check_budget()
        key = tuple(row[n] for n in ('server_id', 'executor_id', 'session_id'))
        lease_rows = by_session.get(key, {})
        try:
            lease = effective_lease_facts(lease_rows.get(1), lease_rows.get(2))
            scope = json.loads(row['expected_revisions_json'])
            lease_scope = json.loads(lease['scope_json']) if lease else None
            exact = (lease_scope == scope and all(scope[n] == row[n] for n in
                ('server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id'))
                and scope['session_id'] == row['session_id'] and scope['session_owner_generation'] == row['owner_generation']
                and scope['binding_revision'] == row['binding_revision'])
            authority_current = bool(exact
                and all(scope[name] == row['current_' + name] for name in
                    ('authorization_revision', 'configuration_revision', 'credential_epoch'))
                and row['enabled'] and row['activation_state'] == 'approved' and row['health'] != 'quarantined'
                and row['is_active'] and row['current_wxb'] == row['workspace_binding_id']
                and row['realization_workspace_binding_id'] == row['workspace_binding_id']
                and row['workspace_status'] == row['realization_status'] == 'READY'
                and row['current_realization_revision'] == row['realization_revision'])
            current = bool(authority_current and lease and lease['status'] == 'ACTIVE' and lease['applied_at']
                and lease['owner_generation'] == row['owner_generation']
                and lease['connection_generation'] == row['generation']
                and lease['connection_id'] == row['owner_instance_id']
                and row['lifecycle_state'] == 'READY' and row['lease_state'] == 'ACTIVE'
                and row['control_state'] == 'CONTROL_READY' and row['revoked_at'] is None and not row['recovering'])
        except (ValueError, TypeError, KeyError, RecursionError):
            lease, current, authority_current = None, False, False
        result.append(SessionRuntimeFact(*(row[n] for n in
            ('server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id',
             'session_id', 'stream_epoch', 'owner_generation', 'lifecycle_state')),
            control_current=current, valid_until=lease['valid_until_server'] if lease else None,
            observed_at=row['observed_at'], workspace_label=(' '.join(redact(row['workspace_label']).split())[:160] or None)
                if type(row['workspace_label']) is str else None,
            revoked=row['revoked_at'] is not None, authority_current=authority_current))
        result[-1] = SessionRuntimeFact(**{**result[-1].__dict__,
            'runtime_ready': bool(current and row['opening_stage'] in ('SUBMITTED', 'SUCCEEDED')
                and row['opening_native_id']
                and row['closing_session_id'] is None and row['gap_state'] == 'none'
                and row['projected_through'] == row['committed_contiguous']),
            'persistent_runtime': row['session_policy'] in ('shared', 'per_sender', 'per_sender_session')})
    return tuple(result)
