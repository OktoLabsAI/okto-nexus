"""One relational facts query for canonical native attention; no per-item I/O."""
import json


def _object(alias, fields):
    return 'json_object(' + ','.join("'" + field + "'," + alias + '.' + field for field in fields.split()) + ')'


def _nullable(alias, key, fields):
    return 'CASE WHEN ' + alias + '.' + key + ' IS NOT NULL THEN ' + _object(alias, fields) + ' END'


def _array(query):
    return "COALESCE((SELECT json_group_array(json(item)) FROM (" + query + ")), '[]')"


_AGENT = 'agent_id role capabilities metadata api_key_hash is_active permissions preset_id tags comm_scope color'
_ENDPOINT = ('endpoint_id agent_id workspace_id adapter_id protocol contract_version profile_id enabled activation_state '
    'health priority selection_group consumption response_policy public_config revision')
_PROFILE = 'profile_id adapter_id config secret_refs inherit_ambient enabled revision'
_GRANT = ('grant_id actor_agent_id credential_binding represented_agent_id endpoint_id workspace_id profile_revision '
    'actions expires_at no_expiry unlimited_actions used_executions max_executions revoked_at revision')
_LEASE = ('lease_serial status request_json scope_json connection_id connection_generation grant_id '
    'source_grant_revision allowed_actions_json applied_at valid_until_server')
_SCOPE = ('server_id executor_id binding_id agent_id workspace_id workspace_binding_id session_id '
    'session_owner_generation authorization_revision configuration_revision binding_revision credential_epoch').split()
_SCOPE_JSON = 'json_object(' + ','.join("'" + key + "',json_extract(r.operational_frame_json,'$." + key + "')" for key in _SCOPE) + ')'

_METHODS = _array('SELECT ' + _object('cm', 'agent_id method enabled') + ' AS item '
    'FROM agent_connection_methods cm WHERE cm.agent_id=a.agent_id ORDER BY cm.method')
_ENDPOINTS = _array('SELECT ' + _object('ep', _ENDPOINT) + ' AS item '
    'FROM agent_endpoints ep WHERE ep.agent_id=a.agent_id ORDER BY ep.endpoint_id')
_PROFILES = _array('SELECT DISTINCT ' + _object('rp', _PROFILE) + ' AS item '
    'FROM runtime_profiles rp JOIN agent_endpoints ep ON ep.profile_id=rp.profile_id '
    'WHERE ep.agent_id=a.agent_id ORDER BY rp.profile_id')
_EXECUTION_POLICY = _array('SELECT ' + _object('xp', 'agent_id execution_location local_adapter_id revision') + ' AS item '
    'FROM agent_execution_policies xp WHERE xp.agent_id=a.agent_id')
_GRANTS = _array('SELECT ' + _object('g', _GRANT) + ' AS item FROM runtime_execution_grants g '
    'WHERE g.endpoint_id=ep.endpoint_id AND g.revoked_at IS NULL AND g.actor_agent_id IN (SELECT agent_id FROM actors) '
    'ORDER BY g.grant_id')

# Agent and endpoint facts are materialized once per distinct authority, not
# once per request. JSON stays inside the read transaction and the classifier;
# no frame, native prompt, response, CAS token or credential is emitted publicly.
SOURCE_SQL = f"""
WITH
requests AS MATERIALIZED (
    SELECT r.* FROM execution_native_requests r
    WHERE (:workspace_id IS NULL OR json_extract(r.operational_frame_json,'$.workspace_id')=:workspace_id)
      AND (:agent_id IS NULL OR json_extract(r.operational_frame_json,'$.agent_id')=:agent_id)
),
live_requests AS MATERIALIZED (
    SELECT r.* FROM requests r JOIN approvals ap ON ap.approval_id=r.canonical_request_id
    WHERE r.state='PENDING' AND julianday(r.expires_at)>julianday(:now) AND ap.status='pending'
      AND ap.archived_at IS NULL
),
session_keys AS MATERIALIZED (SELECT DISTINCT server_id,executor_id,session_id FROM live_requests),
actors AS MATERIALIZED (
    SELECT json_extract(r.operational_frame_json,'$.agent_id') AS agent_id FROM live_requests r
    UNION SELECT op.actor_agent_id FROM live_requests r JOIN execution_sessions s USING(server_id,executor_id,session_id)
        JOIN execution_operations op ON op.server_id=s.server_id AND op.executor_id=s.executor_id AND op.operation_id=s.open_operation_id
    UNION SELECT 'operator' WHERE EXISTS(SELECT 1 FROM live_requests)
),
agent_facts AS MATERIALIZED (
    SELECT a.agent_id, json_object('agent',{_object('a', _AGENT)},
        'methods',json({_METHODS}), 'endpoints',json({_ENDPOINTS}), 'profiles',json({_PROFILES}),
        'execution_policy',json({_EXECUTION_POLICY}),
        'runtime_override',{_nullable('ro', 'agent_id', 'runtime_enabled session_policy')},
        'runtime_epoch',COALESCE(pe.epoch,0)) AS facts
    FROM agents a JOIN actors x ON x.agent_id=a.agent_id
    LEFT JOIN agent_runtime_overrides ro ON ro.agent_id=a.agent_id
    LEFT JOIN agent_runtime_policy_epochs pe ON pe.agent_id=a.agent_id
),
endpoint_bindings AS MATERIALIZED (
    SELECT b.endpoint_id,json_group_array(b.executor_id) AS executors,
        json_group_array(e.kind) AS kinds
    FROM execution_bindings b JOIN execution_installation i ON i.server_id=b.server_id AND i.singleton=1
    LEFT JOIN execution_executors e ON e.server_id=b.server_id AND e.executor_id=b.executor_id
    GROUP BY b.endpoint_id
),
runtime_facts AS MATERIALIZED (
    SELECT ep.endpoint_id,json_object('endpoint',{_object('ep', _ENDPOINT)},
        'profile',{_nullable('rp', 'profile_id', _PROFILE)},'represented',json(af.facts),
        'binding_executors',json(COALESCE(eb.executors,'[]')),
        'host_kinds',json(COALESCE(eb.kinds,'[]')),'grants',json({_GRANTS})) AS facts
    FROM agent_endpoints ep JOIN agent_facts af ON af.agent_id=ep.agent_id
    LEFT JOIN runtime_profiles rp ON rp.profile_id=ep.profile_id
    LEFT JOIN endpoint_bindings eb ON eb.endpoint_id=ep.endpoint_id
),
recipient_bindings AS MATERIALIZED (
    SELECT b.binding_id,ep.agent_id,MIN(b.endpoint_id) AS endpoint_id,COUNT(*) AS bindings
    FROM execution_bindings b JOIN execution_installation i ON i.server_id=b.server_id AND i.singleton=1
    JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id GROUP BY b.binding_id,ep.agent_id
),
ranked_leases AS MATERIALIZED (
    SELECT l.*,ROW_NUMBER() OVER(PARTITION BY l.server_id,l.executor_id,l.session_id ORDER BY l.lease_serial DESC) AS position
    FROM execution_leases l JOIN session_keys k USING(server_id,executor_id,session_id)
),
source_keys AS MATERIALIZED (SELECT DISTINCT server_id,executor_id,source_operation_id FROM live_requests),
ranked_receipts AS MATERIALIZED (
    SELECT rr.*,ROW_NUMBER() OVER(PARTITION BY rr.server_id,rr.executor_id,rr.operation_id ORDER BY rr.receipt_revision DESC) AS position
    FROM execution_receipts rr JOIN source_keys k ON k.server_id=rr.server_id AND k.executor_id=rr.executor_id
        AND k.source_operation_id=rr.operation_id
),
stream_failures AS MATERIALIZED (
    SELECT DISTINCT s.server_id,s.executor_id,s.session_id,s.owner_generation
    FROM execution_sessions s JOIN session_keys k USING(server_id,executor_id,session_id)
    JOIN execution_event_watermarks w USING(server_id,executor_id,session_id,stream_epoch)
    JOIN execution_event_ingress e USING(server_id,executor_id,session_id,stream_epoch)
    WHERE s.lifecycle_state NOT IN ('CLOSED','FAILED') AND e.event_type='error'
      AND e.sequence<=w.committed_contiguous
      AND json_extract(e.payload_json,'$.native_type')='core.event_pump_failed'
      AND json_extract(e.payload_json,'$.payload.code')='EVENT_STREAM_UNAVAILABLE'
)
SELECT json_object(
    'request',json_object('canonical_request_id',r.canonical_request_id,'kind',r.kind,'state',r.state,
        'request_revision',r.request_revision,'stream_epoch',r.stream_epoch,'source_operation_id',r.source_operation_id,
        'received_at',r.received_at,'expires_at',r.expires_at,'scope',{_SCOPE_JSON},
        'method',json_extract(r.operational_frame_json,'$.operational_request.method'),
        'approval_kind',json_extract(r.operational_frame_json,'$.operational_request.params._meta.codex_approval_kind')),
    'approval',CASE WHEN ap.approval_id IS NOT NULL THEN json_object('status',ap.status,
        'decision_revision',ap.decision_revision,'decided_at',ap.decided_at,'archived_at',ap.archived_at,
        'recipient_agent_id',json_extract(ap.request_payload,'$.kwargs.recipient_agent_id')) END,
    'source',{_nullable('turn', 'operation_id', 'action actor_agent_id subject_agent_id expected_revisions_json admission_state')},
    'domain_link_exists',x.operation_id IS NOT NULL,'domain_sender',msg.from_agent_id,
    'session',{_nullable('s', 'session_id', 'stream_epoch lifecycle_state lease_state')},
    'authority',CASE WHEN b.binding_id IS NOT NULL AND ep.endpoint_id IS NOT NULL AND subject.agent_id IS NOT NULL
        AND ex.executor_id IS NOT NULL AND wb.workspace_binding_id IS NOT NULL AND real.realization_ref IS NOT NULL
        AND opening.operation_id IS NOT NULL AND ci.intent_id IS NOT NULL THEN json_object(
        'lifecycle_state',s.lifecycle_state,'lease_state',s.lease_state,'owner_generation',s.owner_generation,
        'binding_id',s.binding_id,'workspace_id',s.workspace_id,'workspace_binding_id',s.workspace_binding_id,
        'endpoint_id',b.endpoint_id,'binding_revision',b.binding_revision,'binding_workspace_binding_id',b.workspace_binding_id,
        'realization_workspace_binding_id',real.workspace_binding_id,'realization_revision',b.realization_revision,
        'current_realization_revision',real.revision,'realization_status',real.status,'subject_agent_id',real.subject_agent_id,
        'agent_id',ep.agent_id,'protocol',ep.protocol,'activation_state',ep.activation_state,'enabled',ep.enabled,
        'health',ep.health,'workspace_status',wb.status,'kind',ex.kind,'control_state',ex.control_state,
        'generation',ex.generation,'owner_instance_id',ex.owner_instance_id,'revoked_at',ex.revoked_at,
        'api_key_hash',subject.api_key_hash,'is_active',subject.is_active,
        'semantic_payload',json_object('action',json_extract(opening.semantic_payload,'$.action'),
            'payload',json_object('mode',json_extract(opening.semantic_payload,'$.payload.mode'))),
        'expected_revisions_json',opening.expected_revisions_json,'admission_state',opening.admission_state,
        'actor_agent_id',opening.actor_agent_id,'source_guard_digest',ci.source_guard_digest,'actor_guard_digest',ci.actor_guard_digest,
        'dispatch_grant_id',dispatch.dispatch_grant_id) END,
    'revisions',{_nullable('rev', 'agent_id', 'credential_epoch authorization_revision configuration_revision')},
    'latest_lease',{_nullable('latest', 'lease_serial', _LEASE)},
    'previous_lease',{_nullable('previous', 'lease_serial', _LEASE)},
    'receipt',{_nullable('receipt', 'receipt_revision', 'stage receipt_revision')},
    'runtime',json(runtime.facts),'subject',json(subject_facts.facts),'initiator',json(initiator.facts),'operator',json(operator.facts),
    'delegated_runtime',CASE WHEN delegated.facts IS NOT NULL THEN
        json_set(delegated.facts,'$.recipient_binding_count',recipient_binding.bindings) END,
    'contained',containment.session_id IS NOT NULL OR failure.session_id IS NOT NULL,
    'recovering',recovery.agent_id IS NOT NULL AND (recovery.state<>'READY' OR recovery.generation<>ex.generation),
    'lane',CASE WHEN lane.binding_id IS NOT NULL AND ticket.ticket_id IS NOT NULL THEN json_object(
        'state',lane.state,'agent_id',lane.agent_id,'connection_id',lane.connection_id,'connection_generation',lane.connection_generation,
        'bound_connection_id',ticket.bound_connection_id,'revoked_at',ticket.revoked_at,'scopes_json',ticket.scopes_json,
        'authorization_revision',lane.authorization_revision,'configuration_revision',lane.configuration_revision,
        'credential_epoch',lane.credential_epoch,'expires_at',lane.expires_at,'ticket_expires_at',ticket.expires_at) END
) AS facts
FROM requests r
LEFT JOIN approvals ap ON ap.approval_id=r.canonical_request_id
LEFT JOIN execution_operations turn ON turn.server_id=r.server_id AND turn.executor_id=r.executor_id AND turn.operation_id=r.source_operation_id
LEFT JOIN execution_domain_deliveries x ON x.server_id=r.server_id AND x.executor_id=r.executor_id AND x.operation_id=r.source_operation_id
LEFT JOIN delivery_outbox d ON d.operation_id=x.domain_operation_id
LEFT JOIN messages msg ON msg.message_id=d.message_id
LEFT JOIN live_requests live ON live.canonical_request_id=r.canonical_request_id
LEFT JOIN execution_sessions s ON live.canonical_request_id IS NOT NULL AND s.server_id=r.server_id AND s.executor_id=r.executor_id AND s.session_id=r.session_id
LEFT JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id AND b.binding_id=s.binding_id
LEFT JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
LEFT JOIN agents subject ON subject.agent_id=ep.agent_id
LEFT JOIN execution_executors ex ON ex.server_id=s.server_id AND ex.executor_id=s.executor_id
LEFT JOIN execution_workspace_bindings wb ON wb.server_id=s.server_id AND wb.executor_id=s.executor_id AND wb.workspace_binding_id=s.workspace_binding_id
LEFT JOIN execution_realizations real ON real.server_id=b.server_id AND real.executor_id=b.executor_id AND real.realization_ref=b.realization_ref
LEFT JOIN execution_operations opening ON opening.server_id=s.server_id AND opening.executor_id=s.executor_id AND opening.operation_id=s.open_operation_id
LEFT JOIN execution_client_intents ci ON ci.server_id=opening.server_id AND ci.actor_agent_id=opening.actor_agent_id
    AND ci.operation_id=opening.operation_id AND ci.intent_id GLOB 'r4intent_*' AND ci.session_selection<>'reuse'
LEFT JOIN execution_dispatch_outbox dispatch ON dispatch.server_id=opening.server_id AND dispatch.executor_id=opening.executor_id AND dispatch.operation_id=opening.operation_id
LEFT JOIN execution_agent_revisions rev ON rev.server_id=r.server_id AND rev.agent_id=json_extract(r.operational_frame_json,'$.agent_id')
LEFT JOIN ranked_leases latest ON latest.server_id=s.server_id AND latest.executor_id=s.executor_id AND latest.session_id=s.session_id AND latest.position=1
LEFT JOIN ranked_leases previous ON previous.server_id=latest.server_id AND previous.executor_id=latest.executor_id AND previous.session_id=latest.session_id AND previous.lease_serial=latest.lease_serial-1
LEFT JOIN ranked_receipts receipt ON receipt.server_id=r.server_id AND receipt.executor_id=r.executor_id AND receipt.operation_id=r.source_operation_id AND receipt.position=1
LEFT JOIN runtime_facts runtime ON runtime.endpoint_id=ep.endpoint_id
LEFT JOIN agent_facts subject_facts ON subject_facts.agent_id=subject.agent_id
LEFT JOIN agent_facts initiator ON initiator.agent_id=opening.actor_agent_id
LEFT JOIN agent_facts operator ON operator.agent_id='operator'
LEFT JOIN recipient_bindings recipient_binding ON recipient_binding.agent_id=json_extract(r.operational_frame_json,'$.agent_id')
    AND recipient_binding.binding_id=CASE WHEN substr(ci.actor_guard_digest,1,10)='delegated:' AND json_valid(substr(ci.actor_guard_digest,11))
        THEN json_extract(substr(ci.actor_guard_digest,11),'$.binding_id') END
LEFT JOIN runtime_facts delegated ON delegated.endpoint_id=recipient_binding.endpoint_id
LEFT JOIN execution_session_containment containment ON containment.server_id=r.server_id AND containment.executor_id=r.executor_id
    AND containment.session_id=r.session_id AND containment.owner_generation=r.session_owner_generation AND containment.state='REQUESTED'
LEFT JOIN stream_failures failure ON failure.server_id=r.server_id AND failure.executor_id=r.executor_id
    AND failure.session_id=r.session_id AND failure.owner_generation=r.session_owner_generation
LEFT JOIN execution_agent_recovery recovery ON recovery.server_id=r.server_id AND recovery.executor_id=r.executor_id
    AND recovery.agent_id=json_extract(r.operational_frame_json,'$.agent_id')
LEFT JOIN execution_control_lanes lane ON lane.server_id=r.server_id AND lane.executor_id=r.executor_id AND lane.binding_id=json_extract(r.operational_frame_json,'$.binding_id')
LEFT JOIN execution_link_tickets ticket ON ticket.ticket_id=lane.ticket_id
"""


def build_policy(uow, *, config, access, context, now):
    from nexus_connector_core import get_runtime_catalog
    operator = access.authenticate(context, uow=uow, require_feature=False)
    defaults = dict(uow.connection.execute(
        "SELECT runtime_enabled,session_policy,(SELECT json_group_object(key,json_object("
        "'value',value,'generation',generation,'changed_at',changed_at)) FROM server_effective_policy) AS effective_policy "
        'FROM runtime_policy_defaults WHERE singleton=1').fetchone())
    effective_policy = json.loads(defaults.pop('effective_policy'))
    values = {key: bool(effective_policy[key]['value']) if key in effective_policy else bool(getattr(config, key))
        for key in ('feature_harness_integrations', 'feature_hitl')}
    return dict(**values, effective_policy=effective_policy,
        admission_closed=bool(access.admission_fence and access.admission_fence.closed),
        viewer_is_operator=operator, viewer_actor=context.actor_agent_id or 'operator', runtime_defaults=defaults,
        catalog={item.adapter_id: dict(connection_mode=item.connection_mode, native_kind=item.native_kind)
            for item in get_runtime_catalog().runtimes})
