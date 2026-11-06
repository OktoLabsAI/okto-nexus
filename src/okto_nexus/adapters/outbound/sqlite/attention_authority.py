"""Batch-only authority facts for work that still awaits a canonical effect.

The private graph contains configuration and digests, never message bodies,
native answers, capability secrets or provider credentials. It lives only in
the authenticated read transaction. Projectors never query this connection.
"""
from . import attention_native as native


_DELIVERY = ('operation_id delivery_id message_id workspace_id actor_agent_id credential_binding recipient_agent_id '
    'endpoint_id endpoint_revision profile_revision runtime_session_id status created_at reconciliation_id admission_binding '
    'authorization_revision source_result_id')
_OPERATION = ('server_id executor_id operation_id subject_agent_id actor_agent_id binding_id workspace_id '
    'workspace_binding_id session_id action expected_revisions_json admission_state created_at connection_key_id boot_authority_json')

SOURCE_SQL = f"""
SELECT json_object('family','delivery','work',{native._object('d', _DELIVERY)}) AS facts
FROM delivery_outbox d
WHERE d.status IN ('PENDING','CLAIMED','RETRY_WAIT') AND d.reconciliation_id IS NULL
  AND d.external_completed_at IS NULL AND d.terminal_event_id IS NULL AND d.canonical_terminal_operation_id IS NULL
  AND NOT EXISTS(SELECT 1 FROM execution_delivery_releases released WHERE released.domain_operation_id=d.operation_id)
  AND EXISTS(SELECT 1 FROM message_deliveries claim WHERE claim.delivery_id=d.delivery_id
      AND claim.consumer_kind='push' AND claim.consumer_operation_id=d.operation_id AND claim.status='unread')
  AND (:workspace_id IS NULL OR d.workspace_id=:workspace_id)
  AND (:agent_id IS NULL OR d.recipient_agent_id=:agent_id)
  AND (EXISTS(SELECT 1 FROM runtime_handoff_bindings h WHERE h.operation_id=d.operation_id) OR NOT EXISTS (SELECT 1 FROM execution_domain_deliveries x JOIN execution_dispatch_outbox q
      USING(server_id,executor_id,operation_id) WHERE x.domain_operation_id=d.operation_id
      AND q.dispatch_state IN ('PENDING','RESERVED')))
UNION ALL
SELECT json_object('family','dispatch','work',{native._object('o', _OPERATION)},
    'profile_revision',json_extract(o.semantic_payload,'$.payload.profile_revision'),
    'native_request_id',json_extract(o.semantic_payload,'$.payload.canonical_request_id')) AS facts
FROM execution_operations o JOIN execution_dispatch_outbox q USING(server_id,executor_id,operation_id)
WHERE o.admission_state IN ('ACCEPTED','DISPATCH_PENDING') AND q.dispatch_state IN ('PENDING','RESERVED')
  AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
  AND (:agent_id IS NULL OR o.subject_agent_id=:agent_id)
  AND NOT EXISTS (SELECT 1 FROM execution_receipts r WHERE r.server_id=o.server_id AND r.executor_id=o.executor_id
      AND r.operation_id=o.operation_id)
  AND NOT EXISTS (SELECT 1 FROM execution_domain_deliveries x JOIN runtime_handoff_bindings h
      ON h.operation_id=x.domain_operation_id WHERE x.server_id=o.server_id AND x.executor_id=o.executor_id AND x.operation_id=o.operation_id)
UNION ALL
SELECT json_object('family','native','native',json(n.facts)) AS facts
FROM ({native.SOURCE_SQL}) n
WHERE json_extract(n.facts,'$.request.state')='PENDING'
  AND julianday(json_extract(n.facts,'$.request.expires_at'))>julianday(:now)
  AND json_extract(n.facts,'$.approval.status')='pending'
  AND json_extract(n.facts,'$.approval.archived_at') IS NULL
  AND NOT EXISTS (SELECT 1 FROM execution_operations o JOIN execution_dispatch_outbox q
      USING(server_id,executor_id,operation_id)
      WHERE json_extract(o.semantic_payload,'$.payload.canonical_request_id')=json_extract(n.facts,'$.request.canonical_request_id')
      AND o.action IN ('approval.decide','input.provide') AND q.dispatch_state IN ('PENDING','RESERVED'))
"""

# Every query is executed once per snapshot, independent of occurrence count.
# The relational roots above still apply workspace/agent filters before the
# engine's exact count/keyset projection; no per-root LIMIT hides incidents.
_TABLES = {
    'agents': native._AGENT,
    'agent_connection_methods': 'agent_id method enabled',
    'agent_endpoints': native._ENDPOINT,
    'runtime_profiles': native._PROFILE + ' launch_revision',
    'agent_execution_policies': 'agent_id execution_location local_adapter_id revision',
    'agent_runtime_overrides': 'agent_id runtime_enabled session_policy broadcast_handoff_auto_claim handoff_auto_claim_epoch',
    'agent_runtime_policy_epochs': 'agent_id epoch',
    'runtime_execution_grants': native._GRANT,
    'execution_installation': 'server_id',
    'execution_bindings': 'server_id executor_id binding_id endpoint_id workspace_binding_id binding_revision realization_ref realization_revision',
    'execution_executors': 'server_id executor_id kind control_state revoked_at generation owner_instance_id',
    'execution_agent_revisions': 'server_id agent_id authorization_revision configuration_revision credential_epoch',
    'execution_workspace_bindings': 'server_id executor_id workspace_binding_id workspace_id status',
    'execution_realizations': 'server_id executor_id realization_ref workspace_binding_id subject_agent_id status revision',
    'execution_sessions': 'server_id executor_id session_id binding_id workspace_id workspace_binding_id open_operation_id owner_generation lifecycle_state lease_state',
    'execution_client_intents': 'server_id actor_agent_id operation_id intent_id session_selection source_guard_digest actor_guard_digest',
    'execution_leases': 'server_id executor_id session_id ' + native._LEASE,
    'execution_session_capabilities': 'capability_id audience scope_json actions_json revoked_at valid_until_server source_grant_id source_grant_revision',
    'runtime_handoff_notifications': 'message_id actor_guard runtime_route handoff_id recipient_agent_id event_type',
    'runtime_handoff_bindings': 'operation_id handoff_id claim_epoch grant_id grant_revision idempotency_key',
    'handoffs': 'handoff_id status claimed_by claim_epoch workspace_id from_agent_id target visibility created_at',
    'handoff_authorization_receipts': 'handoff_id creator_policy_revision hitl_enabled',
    'agent_policy_bindings': 'agent_id position source policy_id mode pinned_version audience governance',
    'policy_versions': 'policy_id version audience governance published_at',
    'runtime_boot_bindings': 'endpoint_id enabled endpoint_revision profile_revision issuer_agent_id issuer_credential_binding revision',
    'execution_domain_deliveries': 'server_id executor_id operation_id domain_operation_id',
    'execution_dispatch_outbox': 'server_id executor_id operation_id dispatch_grant_id',
    'delivery_outbox': _DELIVERY,
    'harness_sessions': 'session_id runtime_profile_revision',
    'runtime_results': 'result_id operation_id publication_state publication_approval_id delivery_outcome',
}


def _anchor(table, keys, columns):
    def identity(prefix):
        return 'json_array(' + ','.join(prefix + '.' + key for key in keys) + ')'
    def state(prefix):
        return 'json_array(' + ','.join(prefix + '.' + key for key in columns) + ')'
    kind = 'authority_' + table
    clock = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
    return f"""
INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT '{kind}',{identity('r')},'present',1,{clock},{clock} FROM {table} r;
CREATE TRIGGER attention_authority_{table}_insert AFTER INSERT ON {table} BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('{kind}',{identity('NEW')},'present',1,{clock},{clock}) ON CONFLICT(source_type,source_id) DO UPDATE SET state='present',episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_authority_{table}_update AFTER UPDATE OF {','.join(columns)} ON {table} WHEN {state('OLD')} IS NOT {state('NEW')} BEGIN UPDATE attention_operation_epochs SET state='present',episode=episode+1,first_detected_at={clock},last_changed_at={clock} WHERE source_type='{kind}' AND source_id={identity('NEW')}; END;
CREATE TRIGGER attention_authority_{table}_delete AFTER DELETE ON {table} BEGIN UPDATE attention_operation_epochs SET state='deleted',episode=episode+1,first_detected_at={clock},last_changed_at={clock} WHERE source_type='{kind}' AND source_id={identity('OLD')}; END;
"""


def _anchor_schema():
    from ....application.attention_authority import KEYS
    sources = {name: keys for name, keys in KEYS.items() if name not in {
        'messages', 'delivery_outbox', 'execution_domain_deliveries', 'execution_operations',
        'runtime_handoff_notifications', 'runtime_handoff_bindings', 'handoffs', 'runtime_results', 'execution_decisions', 'execution_dispatch_outbox'}}
    sources.update(agent_connection_methods=('agent_id', 'method'), agent_execution_policies=('agent_id',),
        runtime_policy_defaults=('singleton',), agent_policy_bindings=('agent_id','position'), policy_versions=('policy_id','version'))
    statements = []
    for table, keys in sources.items():
        columns = ('singleton', 'runtime_enabled', 'session_policy', 'broadcast_handoff_auto_claim', 'handoff_auto_claim_epoch') if table == 'runtime_policy_defaults' else tuple(_TABLES[table].split())
        if table == 'execution_executors':
            columns = tuple(column for column in columns if column != 'control_state')
        statements.append(_anchor(table, keys, columns))
    return ''.join(statements)


ANCHOR_SCHEMA_SQL = _anchor_schema()


def build_policy(uow, *, config, access, context, now, check_budget=None):
    check = check_budget or (lambda: None)
    def read(sql):
        check()
        result = []
        for index, row in enumerate(uow.connection.execute(sql)):
            if index % 128 == 0:
                check()
            result.append(dict(row))
        return result
    policy = native.build_policy(uow, config=config, access=access, context=context, now=now)
    # A process draining or waiting for a channel is availability, not a
    # revoked authority. These reads never create work or bypass the fence.
    policy['admission_closed'] = False
    policy['automation_defaults'] = dict(uow.connection.execute(
        'SELECT broadcast_handoff_auto_claim,handoff_auto_claim_epoch FROM runtime_policy_defaults WHERE singleton=1').fetchone())
    rows = {table: read('SELECT ' + ','.join(fields.split()) + ' FROM ' + table)
        for table, fields in _TABLES.items()}
    rows['execution_operations'] = read(
        'SELECT ' + ','.join(_OPERATION.split()) + ",json_extract(semantic_payload,'$.action') AS semantic_action,"
        "json_extract(semantic_payload,'$.payload.mode') AS mode,json_extract(semantic_payload,'$.payload.profile_revision') AS profile_revision FROM execution_operations")
    rows['pending_dispatch'] = read("SELECT q.server_id,q.executor_id,q.operation_id FROM execution_dispatch_outbox q "
        "JOIN execution_operations o USING(server_id,executor_id,operation_id) WHERE q.dispatch_state IN ('PENDING','RESERVED') "
        "AND o.admission_state IN ('ACCEPTED','DISPATCH_PENDING') AND NOT EXISTS(SELECT 1 FROM execution_receipts r "
        "WHERE r.server_id=o.server_id AND r.executor_id=o.executor_id AND r.operation_id=o.operation_id)")
    rows['messages'] = read(
        "SELECT m.message_id,m.from_agent_id,m.workspace_id,m.target,m.channel_id,CASE WHEN json_valid(m.body) "
        "THEN json_extract(m.body,'$.previous_claimed_by') END AS previous_claimed_by FROM messages m "
        'WHERE EXISTS(SELECT 1 FROM delivery_outbox d WHERE d.message_id=m.message_id) '
        'OR EXISTS(SELECT 1 FROM runtime_handoff_notifications n WHERE n.message_id=m.message_id)')
    rows['runtime_results'] = read(
        'SELECT result_id,operation_id,publication_state,publication_approval_id,delivery_outcome,'
        "json_extract(publication_response,'$.recipients') AS publication_recipients FROM runtime_results")
    rows['execution_decisions'] = read("SELECT d.native_operation_id,d.actor_agent_id,d.actor_guard_digest,d.canonical_request_id,"
        "r.expires_at,r.kind,CASE WHEN r.state='DECIDED' AND a.action='execution.native.respond' "
        "AND a.status=CASE WHEN d.decision='accept' THEN 'approved' ELSE 'rejected' END "
        "AND a.decided_by=d.actor_agent_id AND d.proposal_json=r.operational_frame_json AND d.proposal_digest=r.request_hash "
        "THEN 1 ELSE 0 END AS source_valid FROM execution_decisions d "
        "LEFT JOIN execution_native_requests r ON r.canonical_request_id=d.canonical_request_id "
        "LEFT JOIN approvals a ON a.approval_id=d.canonical_request_id")
    rows['anchors'] = read(
        "SELECT source_type,source_id,episode,first_detected_at,last_changed_at FROM attention_operation_epochs "
        "WHERE source_type LIKE 'authority_%' OR source_type IN ('runtime_grant_revision','runtime_endpoint_revision','runtime_profile_revision')")
    from ....application.attention_authority import prepare_graph
    policy['graph'] = prepare_graph(rows, check_budget=check)
    return policy
