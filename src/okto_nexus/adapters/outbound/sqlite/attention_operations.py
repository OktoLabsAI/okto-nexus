"""Batch metadata sources and write-time episode anchors for attention.

ANCHOR_SCHEMA_SQL is incorporated into migration 161, never executed by a
GET. Backfill timestamps mean first stored observation, not an invented
historical transition time. SQLite's UTC clock matches receipt persistence.
"""
import json

from ....application.attention_operations import handoff_eligible, operator_policy


SQL_FUNCTIONS = (("nexus_attention_handoff_eligible_v1", 2, handoff_eligible),)


def _anchor_statements(table, source_type, identity, state):
    new_id = identity.replace("row.", "NEW.")
    old_id = identity.replace("row.", "OLD.")
    columns = (state,) if isinstance(state, str) else state

    def state_value(prefix):
        values = [prefix + "." + column for column in columns]
        return values[0] if len(values) == 1 else "json_array(" + ",".join(values) + ")"

    row_state, new_state, old_state = (state_value(prefix) for prefix in ("row", "NEW", "OLD"))
    return f"""
INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT '{source_type}',{identity},{row_state},1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM {table} row;
CREATE TRIGGER attention_{table}_insert AFTER INSERT ON {table} BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('{source_type}',{new_id},{new_state},1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state=excluded.state,episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_{table}_state AFTER UPDATE OF {','.join(columns)} ON {table} WHEN {old_state} IS NOT {new_state} BEGIN UPDATE attention_operation_epochs SET state={new_state},episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='{source_type}' AND source_id={new_id}; END;
CREATE TRIGGER attention_{table}_delete AFTER DELETE ON {table} BEGIN DELETE FROM attention_operation_epochs WHERE source_type='{source_type}' AND source_id={old_id}; END;
"""


ANCHOR_SCHEMA_SQL = """
CREATE TABLE attention_operation_epochs (
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    state TEXT NOT NULL,
    episode INTEGER NOT NULL CHECK(episode >= 1),
    first_detected_at TEXT NOT NULL,
    last_changed_at TEXT NOT NULL,
    PRIMARY KEY(source_type,source_id)
);
CREATE INDEX attention_parked_delivery ON message_deliveries(status,recipient_agent_id,delivery_id);
CREATE INDEX attention_pending_recovery ON runtime_pending_deliveries(status,delivery_id);
""" + "".join(_anchor_statements(*args) for args in (
    ("message_deliveries", "message_delivery", "row.delivery_id", "status"),
    ("runtime_pending_deliveries", "runtime_pending_delivery", "row.delivery_id", "status"),
    ("execution_executors", "execution_executor", "json_array(row.server_id,row.executor_id)", "control_state"),
    ("execution_dispatch_outbox", "execution_dispatch", "json_array(row.server_id,row.executor_id,row.operation_id)", "dispatch_state"),
    # Authority revisions have no reliable immutable timestamp on their source
    # rows: grants lack updated_at, and endpoint/profile observations can touch
    # it without changing configuration. Only authority fields advance these
    # anchors, including retirement/disable paths that do not bump revision.
    ("runtime_execution_grants", "runtime_grant_revision", "row.grant_id", "revision"),
    ("agent_endpoints", "runtime_endpoint_revision", "row.endpoint_id", ("revision", "enabled", "activation_state")),
    ("runtime_profiles", "runtime_profile_revision", "row.profile_id", ("revision", "enabled")),
))


OPERATOR_POLICY_SQL = """
SELECT json_object('agent_id',agent_id,'role',role,'is_active',is_active,
    'capabilities',json(COALESCE(capabilities,'[]')),'tags',json(COALESCE(tags,'null')),
    'permissions',json(COALESCE(permissions,'null'))) AS facts
FROM agents WHERE agent_id=:operator_id
"""


def build_policy(uow, *, config, access, context, now):
    """Read current operator metadata once, inside the authenticated snapshot."""
    explicit_actor = getattr(context, "actor_agent_id", None)
    operator_id = explicit_actor or "operator"
    row = uow.connection.execute(OPERATOR_POLICY_SQL, {"operator_id": operator_id}).fetchone()
    # The verifier endpoint binds explicit agent keys, while the authenticated
    # local/browser operator uses the canonical implicit operator identity.
    return operator_policy(json.loads(row["facts"]) if row else None,
                           operator_id=operator_id, require_active=bool(explicit_actor)) | {
        "handoff_unclaimed_seconds": getattr(config, "attention_unclaimed_seconds", None),
        "executor_disconnected_seconds": getattr(config, "attention_disconnected_seconds", None),
    }


# Filters restrict canonical rows before relationship aggregates and before
# the outer engine calls the pure classifier. No per-source LIMIT may hide
# occurrences from exact summary counts or the final keyset page.
SOURCE_SQL = """
WITH operations AS (
    SELECT o.*,x.dispatch_state,x.attempt_no,
        r.stage,r.receipt_revision,r.received_at,
        CASE WHEN r.stage IN ('SUCCEEDED','FAILED','CANCELLED')
                   OR x.dispatch_state IN ('RESOLVED_TERMINAL','RESOLVED_NOT_SENT')
             THEN 0 ELSE 1 END pending
    FROM execution_operations o
    JOIN execution_dispatch_outbox x USING(server_id,executor_id,operation_id)
    LEFT JOIN execution_receipts r ON r.server_id=o.server_id AND r.executor_id=o.executor_id
        AND r.operation_id=o.operation_id AND r.receipt_revision=(
            SELECT max(l.receipt_revision) FROM execution_receipts l
            WHERE l.server_id=o.server_id AND l.executor_id=o.executor_id AND l.operation_id=o.operation_id)
    WHERE (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
      AND (:agent_id IS NULL OR o.subject_agent_id=:agent_id)
), authority AS (
    SELECT o.operation_id,o.workspace_id,o.recipient_agent_id,o.runtime_session_id,
        o.status,o.created_at,b.grant_id,b.grant_revision,
        o.endpoint_revision,o.profile_revision,
        g.revoked_at,g.expires_at,g.no_expiry,g.revision current_grant_revision,
        e.revision current_endpoint_revision,e.enabled endpoint_enabled,e.activation_state,
        p.revision current_profile_revision,p.enabled profile_enabled,
        ga.episode grant_episode,ga.first_detected_at grant_changed_at,
        ea.episode endpoint_episode,ea.first_detected_at endpoint_changed_at,
        pa.episode profile_episode,pa.first_detected_at profile_changed_at,
        CASE WHEN g.revoked_at IS NOT NULL THEN 'grant_revoked'
             WHEN g.no_expiry=0 AND julianday(g.expires_at)<=julianday(:now) THEN 'grant_expired'
             WHEN g.revision<>b.grant_revision THEN 'grant_changed'
             WHEN e.revision<>o.endpoint_revision OR e.enabled=0 OR e.activation_state<>'approved'
                  THEN 'endpoint_changed'
             WHEN o.profile_revision IS NOT NULL AND (p.revision IS NOT o.profile_revision OR p.enabled=0)
                  THEN 'profile_changed' END blocked_reason
    FROM delivery_outbox o JOIN runtime_handoff_bindings b USING(operation_id)
    JOIN handoffs h ON h.handoff_id=b.handoff_id AND h.claim_epoch=b.claim_epoch
        AND h.claimed_by=o.recipient_agent_id AND h.status='CLAIMED'
    JOIN runtime_execution_grants g USING(grant_id)
    JOIN agent_endpoints e ON e.endpoint_id=o.endpoint_id
    LEFT JOIN runtime_profiles p ON p.profile_id=e.profile_id
    LEFT JOIN attention_operation_epochs ga ON ga.source_type='runtime_grant_revision'
        AND ga.source_id=g.grant_id
    LEFT JOIN attention_operation_epochs ea ON ea.source_type='runtime_endpoint_revision'
        AND ea.source_id=e.endpoint_id
    LEFT JOIN attention_operation_epochs pa ON pa.source_type='runtime_profile_revision'
        AND pa.source_id=p.profile_id
    WHERE o.status IN ('PENDING','CLAIMED','RETRY_WAIT') AND o.reconciliation_id IS NULL
      AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
      AND (:agent_id IS NULL OR o.recipient_agent_id=:agent_id)
), blocked_authority AS (
    SELECT a.*,
        CASE blocked_reason WHEN 'grant_revoked' THEN revoked_at WHEN 'grant_expired' THEN expires_at
             WHEN 'grant_changed' THEN grant_changed_at WHEN 'endpoint_changed' THEN endpoint_changed_at
             WHEN 'profile_changed' THEN profile_changed_at END authority_changed_at,
        CASE blocked_reason WHEN 'grant_changed' THEN grant_episode
             WHEN 'endpoint_changed' THEN endpoint_episode WHEN 'profile_changed' THEN profile_episode END authority_episode
    FROM authority a WHERE blocked_reason IS NOT NULL
), available_handoffs AS (
    SELECT h.*,
        (SELECT d.updated_at FROM handoff_dependencies edge JOIN handoffs d ON d.handoff_id=edge.depends_on_id
         WHERE edge.handoff_id=h.handoff_id ORDER BY julianday(d.updated_at) DESC LIMIT 1) last_dependency_at
    FROM handoffs h LEFT JOIN agents creator ON creator.agent_id=h.from_agent_id
    WHERE h.status='OPEN' AND h.claimed_by IS NULL
      AND (:workspace_id IS NULL OR h.workspace_id=:workspace_id)
      AND (:agent_id IS NULL OR h.from_agent_id=:agent_id OR
          (json_extract(h.target,'$.strategy') IN ('direct','direct_with_fallback') AND json_extract(h.target,'$.agent_id')=:agent_id))
      AND NOT EXISTS(SELECT 1 FROM handoff_dependencies edge LEFT JOIN handoffs d ON d.handoff_id=edge.depends_on_id
          WHERE edge.handoff_id=h.handoff_id AND d.status IS NOT 'COMPLETED')
      AND EXISTS(SELECT 1 FROM agents candidate WHERE candidate.is_active=1
          AND nexus_attention_handoff_eligible_v1(json_object(
              'handoff',json_object('workspace_id',h.workspace_id,'target',json(h.target),
                  'visibility',h.visibility,'created_at',h.created_at),
              'creator',json_object('agent_id',h.from_agent_id,'tags',json(COALESCE(creator.tags,'null')),
                  'comm_scope',json(COALESCE(creator.comm_scope,'null'))),
              'candidate',json_object('agent_id',candidate.agent_id,'workspace_id',h.workspace_id,
                  'role',candidate.role,'is_active',candidate.is_active,
                  'capabilities',json(COALESCE(candidate.capabilities,'[]')),
                  'tags',json(COALESCE(candidate.tags,'null')),
                  'comm_scope',json(COALESCE(candidate.comm_scope,'null')),
                  'permissions',json(COALESCE(candidate.permissions,'null')))),:now)=1)
), waiting_handoffs AS (
    SELECT h.*,CASE WHEN julianday(last_dependency_at)>julianday(COALESCE(updated_at,created_at))
                   THEN last_dependency_at ELSE COALESCE(updated_at,created_at) END waiting_since
    FROM available_handoffs h
)
SELECT json_object(
    'family','verification','source_type','handoff','source_id',h.handoff_id,
    'episode',h.claim_epoch,'source_revision',json_array(h.status,h.claim_epoch),
    'first_detected_at',COALESCE(h.updated_at,h.created_at),'last_changed_at',COALESCE(h.updated_at,h.created_at),
    'workspace_id',h.workspace_id,'agent_id',h.claimed_by,'status',h.status,
    'from_agent_id',h.from_agent_id,'claimed_by',h.claimed_by,
    'target',json(h.target),'visibility',h.visibility,'created_at',h.created_at,
    'verify_by',json(h.verify_by)) AS facts
FROM handoffs h WHERE h.status='VERIFYING'
    AND (:workspace_id IS NULL OR h.workspace_id=:workspace_id)
    AND (:agent_id IS NULL OR h.claimed_by=:agent_id OR h.from_agent_id=:agent_id)
UNION ALL
SELECT json_object(
    'family','unknown','source_type','execution_operation','source_id',o.operation_id,
    'episode',json_array(o.server_id,o.executor_id,a.episode),
    'source_revision',json_array(o.dispatch_state,o.receipt_revision,o.stage),
    'first_detected_at',a.first_detected_at,'last_changed_at',
        CASE WHEN julianday(o.received_at)>julianday(a.last_changed_at) THEN o.received_at ELSE a.last_changed_at END,
    'workspace_id',o.workspace_id,'agent_id',o.subject_agent_id,'session_id',o.session_id,
    'operation_id',o.operation_id,'uncertain',1)
FROM operations o JOIN attention_operation_epochs a
    ON a.source_type='execution_dispatch' AND a.source_id=json_array(o.server_id,o.executor_id,o.operation_id)
WHERE o.pending=1 AND (o.stage='OUTCOME_UNKNOWN' OR o.dispatch_state='RECONCILING')
UNION ALL
SELECT json_object(
    'family','parked','source_type','message_delivery','source_id',d.delivery_id,
    'episode',a.episode,'source_revision',json_array(a.episode,d.status),
    'first_detected_at',a.first_detected_at,'last_changed_at',a.last_changed_at,
    'workspace_id',m.workspace_id,'agent_id',d.recipient_agent_id,'status',d.status)
FROM message_deliveries d JOIN messages m USING(message_id)
JOIN attention_operation_epochs a ON a.source_type='message_delivery' AND a.source_id=d.delivery_id
WHERE d.status='parked' AND (:workspace_id IS NULL OR m.workspace_id=:workspace_id)
    AND (:agent_id IS NULL OR d.recipient_agent_id=:agent_id)
UNION ALL
SELECT json_object(
    'family','recovery','source_type','runtime_pending_delivery','source_id',p.delivery_id,
    'episode',a.episode,'source_revision',json_array(a.episode,p.status,p.reason),
    'first_detected_at',a.first_detected_at,'last_changed_at',a.last_changed_at,
    'workspace_id',m.workspace_id,'agent_id',d.recipient_agent_id,'status',p.status,'delivery_pending',1)
FROM runtime_pending_deliveries p JOIN message_deliveries d USING(delivery_id)
JOIN messages m USING(message_id)
JOIN attention_operation_epochs a ON a.source_type='runtime_pending_delivery' AND a.source_id=p.delivery_id
WHERE p.status='attention' AND d.status='unread' AND d.consumer_kind IS NULL
    AND NOT EXISTS(SELECT 1 FROM delivery_outbox o WHERE o.delivery_id=d.delivery_id)
    AND (:workspace_id IS NULL OR m.workspace_id=:workspace_id)
    AND (:agent_id IS NULL OR d.recipient_agent_id=:agent_id)
UNION ALL
SELECT json_object(
    'family','authority','source_type','delivery_operation','source_id',o.operation_id,
    'episode',json(CASE WHEN o.authority_episode IS NOT NULL THEN
        json_array(o.grant_id,o.grant_revision,o.endpoint_revision,o.profile_revision,o.blocked_reason,o.authority_episode)
        ELSE json_array(o.grant_id,o.grant_revision,o.endpoint_revision,o.profile_revision) END),
    'source_revision',json_array(o.blocked_reason,o.current_grant_revision,o.current_endpoint_revision,o.current_profile_revision,o.authority_episode),
    'first_detected_at',CASE WHEN o.authority_episode IS NOT NULL
         AND julianday(o.created_at)>julianday(o.authority_changed_at) THEN o.created_at ELSE o.authority_changed_at END,
    'last_changed_at',CASE WHEN o.authority_episode IS NOT NULL
         AND julianday(o.created_at)>julianday(o.authority_changed_at) THEN o.created_at ELSE o.authority_changed_at END,
    'workspace_id',o.workspace_id,'agent_id',o.recipient_agent_id,'session_id',o.runtime_session_id,
    'operation_id',o.operation_id,'pending',1,'authority_blocked',1)
FROM blocked_authority o
UNION ALL
SELECT json_object(
    'family','disconnected','source_type','execution_operation','source_id',o.operation_id,
    'episode',json_array(o.server_id,o.executor_id,a.episode),
    'source_revision',json_array(a.episode,e.control_state),
    'first_detected_at',CASE WHEN julianday(o.created_at)>julianday(a.first_detected_at) THEN o.created_at ELSE a.first_detected_at END,
    'last_changed_at',CASE WHEN julianday(o.created_at)>julianday(a.last_changed_at) THEN o.created_at ELSE a.last_changed_at END,
    'workspace_id',o.workspace_id,'agent_id',o.subject_agent_id,'session_id',o.session_id,
    'operation_id',o.operation_id,'control_state',e.control_state,'pending',1)
FROM operations o JOIN execution_executors e USING(server_id,executor_id)
JOIN attention_operation_epochs a ON a.source_type='execution_executor' AND a.source_id=json_array(o.server_id,o.executor_id)
WHERE e.control_state='DISCONNECTED' AND o.pending=1
    AND o.dispatch_state IN ('PENDING','RESERVED','SENDING','DISPATCHED','RECONCILING')
    AND NOT EXISTS(SELECT 1 FROM one_shot_slots idle WHERE idle.call_id IS NULL
        AND idle.server_id=o.server_id AND idle.executor_id=o.executor_id
        AND (idle.open_operation_id=o.operation_id OR idle.close_operation_id=o.operation_id))
UNION ALL
SELECT json_object(
    'family','result','source_type','execution_result','source_id',r.operation_id,
    'episode',json_array(r.server_id,r.executor_id,r.stream_epoch,r.terminal_sequence),
    'source_revision',json_array(r.stream_epoch,r.terminal_sequence,r.delivery_outcome),
    'first_detected_at',r.captured_at,'last_changed_at',r.captured_at,
    'workspace_id',o.workspace_id,'agent_id',o.subject_agent_id,'session_id',r.session_id,
    'operation_id',r.operation_id,'canonical_result',1)
FROM execution_results r JOIN execution_operations o USING(server_id,executor_id,operation_id)
WHERE r.terminal_sequence IS NOT NULL AND r.delivery_outcome IN ('success','failed','interrupted')
    AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
    AND (:agent_id IS NULL OR o.subject_agent_id=:agent_id)
UNION ALL
SELECT json_object(
    'family','aged','source_type','handoff','source_id',h.handoff_id,'episode',h.claim_epoch,
    'source_revision',json_array(h.claim_epoch,h.waiting_since,h.status),
    'first_detected_at',h.waiting_since,'last_changed_at',h.waiting_since,
    'workspace_id',h.workspace_id,'agent_id',h.from_agent_id,'status',h.status,'eligible',1)
FROM waiting_handoffs h
UNION ALL
SELECT json_object(
    'family','cleanup','source_type','runtime_result_maintenance','source_id',m.maintenance_id,
    'episode',json_array(m.result_id,m.artifact_generation),
    'source_revision',json_array(m.status,m.attention_failure_code,m.artifact_generation),
    'first_detected_at',m.attention_failure_at,'last_changed_at',m.attention_failure_at,
    'workspace_id',m.workspace_id,'agent_id',m.agent_id,'operation_id',r.canonical_operation_id,
    'status',m.status,'productive_outcome',r.delivery_outcome,'failure_code',m.attention_failure_code)
FROM runtime_result_maintenance m JOIN runtime_results r USING(result_id)
WHERE m.action='cleanup' AND m.status='PENDING'
    AND m.attention_failure_at IS NOT NULL AND m.attention_failure_code='ARTIFACT_CLEANUP_UNCONFIRMED'
    AND r.delivery_outcome='success'
    AND (:workspace_id IS NULL OR m.workspace_id=:workspace_id)
    AND (:agent_id IS NULL OR m.agent_id=:agent_id)
"""
