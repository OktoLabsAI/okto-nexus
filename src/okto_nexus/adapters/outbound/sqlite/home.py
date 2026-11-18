"""Bounded HOME read relations. No domain writes, host calls or transcript reads."""
from contextlib import contextmanager
from datetime import timedelta
import json
from ....domain.home_delivery_semantics import project as delivery_semantics
import time

from ....domain.attention import canonical, digest, instant
from ....domain.home import activity, encode_cursor
from ....errors import ErrorCode, OktoNexusError
from ..harness.event_journal import redact
from .attention import _SetDigest


# Current and historic links are deduplicated before joining receipts. A claim's
# operations are attached only to that epoch, never to a later owner of the work.
# Canonical event commit projects and advances committed_contiguous atomically;
# projected_through is retained schema with no writer. Eligible session history
# is scanned once. Malformed legacy JSON delegates to the old EXISTS so its
# short-circuit/error behavior is preserved, rather than silently dropping it.
# The work composer saves its explicit subject on the operator's structured
# handoff. Project only that bounded label, never the message body or prompt.
FACTS = """
WITH links AS MATERIALIZED (
 SELECT server_id,executor_id,operation_id,domain_operation_id FROM execution_domain_deliveries
 UNION SELECT server_id,executor_id,operation_id,domain_operation_id FROM execution_delivery_attempt_history
), progress_sessions AS MATERIALIZED (
 SELECT DISTINCT o.server_id,o.executor_id,o.session_id,s.stream_epoch
 FROM execution_operations o JOIN execution_sessions s USING(server_id,executor_id,session_id)
 JOIN execution_receipts r ON r.server_id=o.server_id AND r.executor_id=o.executor_id AND r.operation_id=o.operation_id
  AND r.receipt_revision=(SELECT MAX(rr.receipt_revision) FROM execution_receipts rr
   WHERE rr.server_id=o.server_id AND rr.executor_id=o.executor_id AND rr.operation_id=o.operation_id)
 WHERE o.server_id=:server_id AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
  AND o.action='turn.submit' AND s.lifecycle_state IN ('READY','ACTIVE') AND s.lease_state='ACTIVE'
  AND r.stage NOT IN ('SUCCEEDED','FAILED','CANCELLED','OUTCOME_UNKNOWN','REFUSED_BEFORE_EFFECT')
  AND json_extract(o.expected_revisions_json,'$.session_owner_generation')=s.owner_generation
), progress_keys AS MATERIALIZED (
 SELECT DISTINCT e.server_id,e.executor_id,e.session_id,e.stream_epoch,
  CASE WHEN json_valid(e.payload_json) THEN CAST(json_extract(e.payload_json,'$.operation_id') AS TEXT) END AS operation_id,
  CASE WHEN json_valid(e.payload_json) THEN 0 ELSE 1 END AS malformed
 FROM progress_sessions s JOIN execution_event_watermarks w USING(server_id,executor_id,session_id,stream_epoch)
 JOIN execution_event_ingress e ON e.server_id=s.server_id AND e.executor_id=s.executor_id
  AND e.session_id=s.session_id AND e.stream_epoch=s.stream_epoch AND e.sequence<=w.committed_contiguous
 WHERE w.gap_state='none' AND CASE WHEN json_valid(e.payload_json)
  THEN json_extract(e.payload_json,'$.payload.delivery_phase') IN ('started','progress') ELSE 1 END
), scoped_ops AS MATERIALIZED (
 SELECT o.server_id,o.executor_id,o.operation_id,o.session_id,o.workspace_id,o.subject_agent_id,
   o.binding_id,o.workspace_binding_id,
   s.owner_generation AS progress_owner_generation,
   s.stream_epoch AS progress_stream_epoch,
   o.actor_agent_id,o.admission_state,o.created_at,r.stage,r.received_at,r.receipt_revision,s.lifecycle_state,
   CASE WHEN s.lifecycle_state IN ('READY','ACTIVE') AND s.lease_state='ACTIVE'
     AND r.stage NOT IN ('SUCCEEDED','FAILED','CANCELLED','OUTCOME_UNKNOWN','REFUSED_BEFORE_EFFECT')
     AND json_extract(o.expected_revisions_json,'$.session_owner_generation')=s.owner_generation
     AND CASE WHEN invalid_progress.malformed=1 THEN
       EXISTS(SELECT 1 FROM execution_event_ingress e JOIN execution_event_watermarks w
        USING(server_id,executor_id,session_id,stream_epoch)
        WHERE e.server_id=o.server_id AND e.executor_id=o.executor_id AND e.session_id=o.session_id
         AND e.stream_epoch=s.stream_epoch AND e.sequence<=w.committed_contiguous AND w.gap_state='none'
         AND json_extract(e.payload_json,'$.operation_id')=o.operation_id
         AND json_extract(e.payload_json,'$.payload.delivery_phase') IN ('started','progress'))
       ELSE progress.operation_id IS NOT NULL END
     AND NOT EXISTS(SELECT 1 FROM execution_results x WHERE x.server_id=o.server_id AND x.executor_id=o.executor_id
       AND x.operation_id=o.operation_id AND x.terminal_sequence IS NOT NULL)
     THEN 1 ELSE 0 END AS observed_running,
   CASE WHEN k.state='REQUESTED' THEN 1 ELSE 0 END AS cleanup,
   l.domain_operation_id,b.handoff_id,b.claim_epoch AS linked_epoch,
   CASE WHEN b.handoff_id IS NOT NULL THEN json_array('handoff',b.handoff_id,b.claim_epoch)
        WHEN l.domain_operation_id IS NOT NULL THEN json_array('conversation_turn',l.domain_operation_id)
        ELSE json_array('direct_operation',o.server_id,o.executor_id,o.operation_id) END AS group_key
 FROM execution_operations o
 LEFT JOIN execution_receipts r ON r.server_id=o.server_id AND r.executor_id=o.executor_id AND r.operation_id=o.operation_id
   AND r.receipt_revision=(SELECT MAX(rr.receipt_revision) FROM execution_receipts rr
     WHERE rr.server_id=o.server_id AND rr.executor_id=o.executor_id AND rr.operation_id=o.operation_id)
 LEFT JOIN execution_sessions s USING(server_id,executor_id,session_id)
 LEFT JOIN progress_keys progress ON progress.server_id=o.server_id AND progress.executor_id=o.executor_id
  AND progress.session_id=o.session_id AND progress.stream_epoch=s.stream_epoch AND progress.operation_id=o.operation_id
  AND progress.malformed=0
 LEFT JOIN progress_keys invalid_progress ON invalid_progress.server_id=o.server_id AND invalid_progress.executor_id=o.executor_id
  AND invalid_progress.session_id=o.session_id AND invalid_progress.stream_epoch=s.stream_epoch AND invalid_progress.malformed=1
 LEFT JOIN execution_session_containment k ON k.server_id=s.server_id AND k.executor_id=s.executor_id
   AND k.session_id=s.session_id AND k.owner_generation=s.owner_generation
 LEFT JOIN links l ON l.server_id=o.server_id AND l.executor_id=o.executor_id AND l.operation_id=o.operation_id
 LEFT JOIN runtime_handoff_bindings b ON b.operation_id=l.domain_operation_id
 WHERE o.server_id=:server_id AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
   AND o.action='turn.submit'
), ranked AS MATERIALIZED (
 SELECT *,ROW_NUMBER() OVER(PARTITION BY group_key ORDER BY created_at DESC,operation_id DESC) AS position
 FROM scoped_ops
), grouped AS MATERIALIZED (
 SELECT group_key,COUNT(*) AS attempts,
  SUM(observed_running) AS running,
  NULL AS running_since,
  MAX(COALESCE(received_at,created_at)) AS latest,
  json_group_array(json_object('executor_id',executor_id,'session_id',session_id,'operation_id',operation_id))
    FILTER(WHERE position<=20) AS runtime_refs,
  NULL AS native_progress_current
 FROM ranked GROUP BY group_key
), parents AS MATERIALIZED (
 SELECT 'handoff' AS kind,h.handoff_id AS source_id,h.workspace_id,h.status,h.created_at AS created,
  h.updated_at AS changed,
  COALESCE(NULLIF(substr(t.title,1,160),''), CASE
   WHEN h.from_agent_id='operator' AND length(CAST(h.payload AS BLOB))<=65536 THEN CASE
    WHEN json_valid(h.payload) THEN CASE
     WHEN json_extract(h.payload,'$.kind')='meta_harness.request' AND json_type(h.payload,'$.subject')='text'
     THEN NULLIF(NULLIF(trim(substr(json_extract(h.payload,'$.subject'),1,160)),''),'Meta-harness handoff')
    END
   END
  END) AS title,
  h.from_agent_id AS sender,COALESCE(h.claimed_by,json_extract(h.target,'$.agent_id')) AS recipient,
  NULL AS message_id,NULL AS executor_id,NULL AS session_id,
  json_array('handoff',h.handoff_id,h.claim_epoch) AS group_key,
  CASE WHEN h.status='CLAIMED' AND h.lease_expires_at IS NOT NULL AND julianday(h.lease_expires_at)<=julianday(:home_now) THEN 1 ELSE 0 END AS claim_expired,
  EXISTS(SELECT 1 FROM handoff_dependencies dep LEFT JOIN handoffs predecessor ON predecessor.handoff_id=dep.depends_on_id
    WHERE dep.handoff_id=h.handoff_id AND (predecessor.status IS NULL OR predecessor.status<>'COMPLETED')) AS blocked
 FROM handoffs h LEFT JOIN tasks t ON t.task_id=h.task_id AND t.workspace_id=h.workspace_id
 WHERE (:workspace_id IS NULL OR h.workspace_id=:workspace_id)
 UNION ALL
 SELECT 'conversation_turn',d.operation_id,d.workspace_id,d.status,d.created_at,NULL,
  substr(m.subject,1,160),
  m.from_agent_id,d.recipient_agent_id,m.message_id,NULL,NULL,json_array('conversation_turn',d.operation_id),0,0
 FROM delivery_outbox d JOIN messages m ON m.message_id=d.message_id
 WHERE (:workspace_id IS NULL OR d.workspace_id=:workspace_id)
   AND NOT EXISTS(SELECT 1 FROM runtime_handoff_bindings b WHERE b.operation_id=d.operation_id)
 UNION ALL
 SELECT 'direct_operation',o.operation_id,o.workspace_id,o.admission_state,o.created_at,NULL,NULL,
  o.actor_agent_id,o.subject_agent_id,NULL,o.executor_id,o.session_id,o.group_key,0,0
 FROM scoped_ops o WHERE o.domain_operation_id IS NULL
), facts AS MATERIALIZED (
 SELECT json_object('kind',p.kind,'source_id',p.source_id,'workspace_id',p.workspace_id,'status',p.status,
  'created',p.created,'changed',p.changed,'title',p.title,'title_origin',
  CASE WHEN p.title IS NULL OR p.title='' THEN 'fallback'
       WHEN p.kind='conversation_turn' THEN 'message_subject' ELSE 'canonical_title' END,
  'agent_ids',json_array(p.sender,p.recipient),'message_id',p.message_id,'executor_id',p.executor_id,
  'session_id',p.session_id,'blocked',p.blocked,'claim_expired',p.claim_expired,'running',COALESCE(g.running,0),
  'running_since',g.running_since,'latest',g.latest,'attempt_count',COALESCE(g.attempts,0),
  'runtime_refs',json(COALESCE(g.runtime_refs,'[]')),'stage',last.stage,'receipt_at',last.received_at,
  'cleanup',COALESCE(last.cleanup,0)) AS fact,g.native_progress_current AS native_progress_current
 FROM parents p LEFT JOIN grouped g ON g.group_key=p.group_key
 LEFT JOIN ranked last ON last.group_key=p.group_key AND last.position=1
 WHERE (:agent_id IS NULL OR p.sender=:agent_id OR p.recipient=:agent_id
   OR EXISTS(SELECT 1 FROM scoped_ops ao WHERE ao.group_key=p.group_key AND ao.subject_agent_id=:agent_id))
), projected AS MATERIALIZED (SELECT home_activity_v1(fact,:server_id,
 (SELECT json_group_array(json(item)) FROM home_attention WHERE
 json_extract(item,'$.workspace_id')=json_extract(fact,'$.workspace_id') AND (
 (json_extract(item,'$.source_id')=json_extract(fact,'$.source_id') AND
  json_extract(item,'$.source_type')=CASE json_extract(fact,'$.kind') WHEN 'handoff' THEN 'handoff' WHEN 'conversation_turn' THEN 'delivery_operation' ELSE 'execution_operation' END
  AND (json_extract(fact,'$.kind')<>'direct_operation' OR (
    json_extract(item,'$.executor_id')=json_extract(fact,'$.executor_id') AND
    json_extract(item,'$.session_id')=json_extract(fact,'$.session_id'))))
 OR (json_extract(item,'$.source_type') IN ('execution_native_request','execution_operation','execution_result','handoff_result') AND EXISTS(SELECT 1 FROM json_each(fact,'$.runtime_refs') ref
  WHERE json_extract(item,'$.operation_id')=json_extract(ref.value,'$.operation_id')
    AND json_extract(item,'$.executor_id')=json_extract(ref.value,'$.executor_id')
    AND json_extract(item,'$.session_id')=json_extract(ref.value,'$.session_id')))))) AS item,native_progress_current FROM facts),
filtered AS MATERIALIZED (SELECT item,native_progress_current FROM projected WHERE
 (:state IS NOT NULL AND (:state='all' OR json_extract(item,'$.display_state')=:state)) OR
 (:state IS NULL AND json_extract(item,'$.display_state') NOT IN ('completed','turn_completed','failed','cancelled')))
"""

# Only the internal v2 relation serializes complete positive operation proof.
# Legacy/public queries keep NULL and do not allocate this JSON collection.
FACTS_NATIVE_PROGRESS = FACTS.replace('NULL AS native_progress_current', """
  json_group_array(json_object('server_id',server_id,'executor_id',executor_id,'operation_id',operation_id,
    'session_id',session_id,'workspace_id',workspace_id,'agent_id',subject_agent_id,
    'binding_id',binding_id,'workspace_binding_id',workspace_binding_id,
    'owner_generation',progress_owner_generation,'stream_epoch',progress_stream_epoch))
    FILTER(WHERE observed_running=1) AS native_progress_current""")


RESULTS = """
WITH links AS MATERIALIZED (
 SELECT server_id,executor_id,operation_id,domain_operation_id FROM execution_domain_deliveries
 UNION SELECT server_id,executor_id,operation_id,domain_operation_id FROM execution_delivery_attempt_history
), proof_payloads AS MATERIALIZED (
 SELECT event_id,workspace_id,actor_agent_id,type,
  CASE WHEN NOT json_valid(payload) THEN '{}' WHEN json_type(payload,'$.delivery_ref')='object'
   THEN json_extract(payload,'$.delivery_ref') ELSE '{}' END AS ref,
  json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.handoff_id') AS declared_handoff,
  json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.claim_epoch') AS declared_epoch,
  json_type(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.claim_epoch') AS declared_epoch_type,
  json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.delivery_revision') AS declared_revision,
  json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.verified_by') AS verified_by,
  json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.verification_verdict') AS verdict
 FROM events WHERE stream='handoff' AND type IN ('handoff.completed','handoff.verification_failed','handoff.verification_requested')
  AND (:workspace_id IS NULL OR workspace_id=:workspace_id)
), proof_facts AS MATERIALIZED (
 SELECT event_id,workspace_id,type,json_extract(ref,'$.handoff_id') AS handoff_id,
  json_extract(ref,'$.claim_epoch') AS claim_epoch,
  json_object('version',json_extract(ref,'$.version'),
   'kind',json_extract(ref,'$.kind'),
   'workspace_id',json_extract(ref,'$.workspace_id'),
   'handoff_id',json_extract(ref,'$.handoff_id'),
   'claim_epoch',json_extract(ref,'$.claim_epoch'),
   'delivery_revision',json_extract(ref,'$.delivery_revision'),
   'event_claim_epoch',declared_epoch,
   'event_delivery_revision',declared_revision,
   'event_id',event_id,'event_type',type,'actor_agent_id',actor_agent_id,
   'verified_by',verified_by,'verdict',verdict) AS proof
 FROM proof_payloads WHERE json_type(ref,'$.version')='integer' AND json_extract(ref,'$.version')=1
  AND json_type(ref,'$.claim_epoch')='integer' AND declared_epoch_type='integer'
  AND json_extract(ref,'$.kind')='handoff_delivery'
  AND json_extract(ref,'$.workspace_id')=workspace_id
  AND json_extract(ref,'$.handoff_id')=declared_handoff
  AND json_extract(ref,'$.claim_epoch')=declared_epoch
  AND json_extract(ref,'$.delivery_revision')=declared_revision
), delivery_submissions AS MATERIALIZED (
 SELECT workspace_id,handoff_id,claim_epoch,event_id AS submission_event_id,
  json_extract(proof,'$.delivery_revision') AS delivery_revision
 FROM (SELECT *,ROW_NUMBER() OVER(PARTITION BY workspace_id,handoff_id,claim_epoch ORDER BY event_id DESC) AS submission_position
  FROM proof_facts WHERE type='handoff.verification_requested') WHERE submission_position=1
), last_submission AS MATERIALIZED (
 SELECT workspace_id,handoff_id,MAX(submission_event_id) AS last_submission_event_id
 FROM delivery_submissions GROUP BY workspace_id,handoff_id
), verification_proofs AS MATERIALIZED (
 SELECT workspace_id,handoff_id,claim_epoch,proof FROM (
  SELECT f.workspace_id,f.handoff_id,f.claim_epoch,
   json_set(f.proof,'$.submission_event_id',d.submission_event_id) AS proof,
   ROW_NUMBER() OVER(PARTITION BY f.workspace_id,f.handoff_id,f.claim_epoch ORDER BY f.event_id DESC) AS proof_position
  FROM proof_facts f JOIN delivery_submissions d USING(workspace_id,handoff_id,claim_epoch)
  WHERE f.type IN ('handoff.completed','handoff.verification_failed')
   AND d.delivery_revision=json_extract(f.proof,'$.delivery_revision') AND d.submission_event_id<f.event_id
 ) WHERE proof_position=1
), native_facts AS MATERIALIZED (
 SELECT o.server_id,o.executor_id,o.operation_id,o.session_id,o.workspace_id,o.subject_agent_id,
  r.stage,r.received_at,r.receipt_revision,x.stream_epoch,x.terminal_sequence,x.captured_at,
  CASE WHEN x.terminal_sequence IS NOT NULL THEN substr(x.output_text,1,401) END AS preview,
  x.output_truncated,
  CASE WHEN k.state='REQUESTED' THEN 'pending' END AS cleanup,k.state AS containment_state,
  h.handoff_id,CASE WHEN h.handoff_id IS NOT NULL THEN b.claim_epoch END AS claim_epoch,
  h.claim_epoch AS current_epoch,h.status AS handoff_status,
  d.delivery_revision,
  CASE WHEN h.handoff_id IS NOT NULL THEN json(CASE WHEN h.acceptance_criteria IS NULL THEN 'false' ELSE 'true' END) END AS verification_required,
  substr(t.title,1,160) AS title
 FROM execution_operations o JOIN execution_receipts r USING(server_id,executor_id,operation_id)
 LEFT JOIN execution_results x USING(server_id,executor_id,operation_id)
 LEFT JOIN execution_sessions s USING(server_id,executor_id,session_id)
 LEFT JOIN execution_session_containment k ON k.server_id=s.server_id AND k.executor_id=s.executor_id
  AND k.session_id=s.session_id AND k.owner_generation=s.owner_generation
 LEFT JOIN links l ON l.server_id=o.server_id AND l.executor_id=o.executor_id AND l.operation_id=o.operation_id
 LEFT JOIN runtime_handoff_bindings b ON b.operation_id=l.domain_operation_id
 LEFT JOIN handoffs h ON h.handoff_id=b.handoff_id AND h.workspace_id=o.workspace_id
  LEFT JOIN delivery_submissions d ON d.workspace_id=h.workspace_id AND d.handoff_id=h.handoff_id AND d.claim_epoch=b.claim_epoch
 LEFT JOIN tasks t ON t.task_id=h.task_id AND t.workspace_id=h.workspace_id
 WHERE o.server_id=:server_id AND o.action='turn.submit' AND r.stage IN ('SUCCEEDED','FAILED','CANCELLED')
  AND r.receipt_revision=(SELECT MAX(rr.receipt_revision) FROM execution_receipts rr
   WHERE rr.server_id=o.server_id AND rr.executor_id=o.executor_id AND rr.operation_id=o.operation_id)
  AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
  AND (:agent_id IS NULL OR o.subject_agent_id=:agent_id)
), native AS MATERIALIZED (
 SELECT *,
  CASE WHEN handoff_id IS NOT NULL THEN json_array('handoff',handoff_id,claim_epoch)
       ELSE json_array('execution',server_id,executor_id,operation_id) END AS result_group
 FROM native_facts
), artifact_refs AS MATERIALIZED (
 SELECT DISTINCT n.result_group,n.workspace_id,a.artifact_id,substr(a.name,1,160) AS filename,a.content_type AS media_type
 FROM native n JOIN runtime_results rr ON rr.canonical_server_id=n.server_id
  AND rr.canonical_executor_id=n.executor_id AND rr.canonical_operation_id=n.operation_id
 JOIN artifacts a ON a.artifact_id=rr.output_artifact_id AND a.workspace_id=n.workspace_id
), artifact_arrays AS MATERIALIZED (
 SELECT result_group,workspace_id,json_group_array(json_object('artifact_id',artifact_id,'filename',filename,'media_type',media_type)) AS artifacts
 FROM (SELECT * FROM artifact_refs ORDER BY result_group,workspace_id,artifact_id) GROUP BY result_group,workspace_id
), ranked AS MATERIALIZED (
 SELECT *,ROW_NUMBER() OVER(PARTITION BY result_group,workspace_id
  ORDER BY received_at DESC,operation_id DESC) AS position FROM native
), facts AS MATERIALIZED (
 SELECT json_object('server_id',server_id,'executor_id',executor_id,'session_id',session_id,'operation_id',operation_id,
  'workspace_id',workspace_id,'agent_id',subject_agent_id,'stage',stage,'received_at',received_at,'title',title,
  'revision',receipt_revision,'cleanup',cleanup,'handoff_id',handoff_id,'claim_epoch',claim_epoch,
  'stream_epoch',stream_epoch,'terminal_sequence',terminal_sequence,'preview',preview,
  'truncated',output_truncated,'artifacts',json(COALESCE(artifacts,'[]')),
   'verification',CASE WHEN claim_epoch=current_epoch THEN handoff_status ELSE 'historical_claim' END,
   'current_epoch',current_epoch,'handoff_status',handoff_status,'containment_state',containment_state,
   'verification_required',json(verification_required),'delivery_revision',
     CASE WHEN claim_epoch<>current_epoch AND proof IS NOT NULL THEN json_extract(proof,'$.delivery_revision') ELSE delivery_revision END,
   'verification_proof',json(proof)) AS fact
  FROM ranked LEFT JOIN artifact_arrays USING(result_group,workspace_id)
   LEFT JOIN verification_proofs USING(workspace_id,handoff_id,claim_epoch) WHERE position=1
 UNION ALL
 SELECT json_object('server_id',:server_id,'workspace_id',h.workspace_id,'agent_id',COALESCE(h.claimed_by,h.from_agent_id),
  'handoff_id',h.handoff_id,'claim_epoch',h.claim_epoch,'stage',h.status,'verification',h.status,
  'received_at',COALESCE(h.updated_at,h.created_at),'revision',h.claim_epoch,
   'preview',substr(h.result,1,401),'title',substr(t.title,1,160),
   'current_epoch',h.claim_epoch,'handoff_status',h.status,
   'verification_required',json(CASE WHEN h.acceptance_criteria IS NULL THEN 'false' ELSE 'true' END),
   'handoff_content_available',json(CASE WHEN h.result IS NULL THEN 'false' ELSE 'true' END),
    'delivery_revision',d.delivery_revision,
   'verification_proof',json(v.proof))
 FROM handoffs h LEFT JOIN tasks t ON t.task_id=h.task_id AND t.workspace_id=h.workspace_id
  LEFT JOIN verification_proofs v ON v.workspace_id=h.workspace_id AND v.handoff_id=h.handoff_id AND v.claim_epoch=h.claim_epoch
   LEFT JOIN delivery_submissions d ON d.workspace_id=h.workspace_id AND d.handoff_id=h.handoff_id AND d.claim_epoch=h.claim_epoch
  WHERE (h.status IN ('COMPLETED','REJECTED') OR (:delivery_presentation_version=2 AND h.status='VERIFYING'))
  AND (:workspace_id IS NULL OR h.workspace_id=:workspace_id)
  AND (:agent_id IS NULL OR COALESCE(h.claimed_by,h.from_agent_id)=:agent_id)
  AND NOT EXISTS(SELECT 1 FROM native n WHERE n.handoff_id=h.handoff_id AND n.claim_epoch=h.claim_epoch)
 UNION ALL
 SELECT json_object('server_id',:server_id,'workspace_id',h.workspace_id,'agent_id',COALESCE(h.claimed_by,h.from_agent_id),
  'handoff_id',h.handoff_id,'claim_epoch',v.claim_epoch,'stage','REJECTED','verification','historical_claim',
  'received_at',e.created_at,'revision',e.event_id,'current_epoch',h.claim_epoch,'handoff_status',h.status,
  'delivery_revision',json_extract(v.proof,'$.delivery_revision'),
  'verification_required',json('true'),'verification_proof',json(v.proof),
   'handoff_content_available',json(CASE WHEN json_extract(v.proof,'$.submission_event_id')=last_submission_event_id AND h.result IS NOT NULL THEN 'true' ELSE 'false' END),
   'preview',CASE WHEN json_extract(v.proof,'$.submission_event_id')=last_submission_event_id THEN substr(h.result,1,401) END,
  'title',substr(t.title,1,160))
 FROM verification_proofs v JOIN handoffs h ON h.workspace_id=v.workspace_id AND h.handoff_id=v.handoff_id
  JOIN events e ON e.event_id=json_extract(v.proof,'$.event_id')
   LEFT JOIN last_submission s ON s.workspace_id=h.workspace_id AND s.handoff_id=h.handoff_id
  LEFT JOIN tasks t ON t.task_id=h.task_id AND t.workspace_id=h.workspace_id
 WHERE :delivery_presentation_version=2 AND v.claim_epoch<h.claim_epoch
  AND json_extract(v.proof,'$.verdict')='fail'
  AND (:workspace_id IS NULL OR h.workspace_id=:workspace_id)
  AND (:agent_id IS NULL OR COALESCE(h.claimed_by,h.from_agent_id)=:agent_id)
  AND NOT EXISTS(SELECT 1 FROM native n WHERE n.handoff_id=h.handoff_id AND n.claim_epoch=v.claim_epoch)
), projected AS MATERIALIZED (SELECT home_result_v1(fact) AS item FROM facts),
filtered AS MATERIALIZED (SELECT home_result_attention_v1(item,
 (SELECT item FROM home_attention WHERE json_extract(item,'$.attention_id')=json_extract(projected.item,'$._attention_id'))) AS item FROM projected)
"""


def result_item(raw):
    f = json.loads(raw)
    handoff = f.get('handoff_id')
    key = ['handoff', handoff, f['claim_epoch']] if handoff else ['execution', f['executor_id'], f['operation_id']]
    target = dict(server_id=f['server_id'], workspace_id=f['workspace_id'])
    if f.get('operation_id'):
        target.update(kind='result', executor_id=f['executor_id'], session_id=f['session_id'], operation_id=f['operation_id'])
    else:
        target.update(kind='handoff', handoff_id=handoff)
    episode = f.get('claim_epoch') if handoff else [f['server_id'], f['executor_id'], f.get('stream_epoch'), f.get('terminal_sequence')]
    return canonical(dict(id='result_' + digest([f['server_id'], key]),
        source_ref=dict(type='handoff_result' if handoff else 'execution_result',
            id=handoff or f['operation_id'], revision=digest(f)), workspace_id=f['workspace_id'], agent_id=f['agent_id'],
        title=redact(f.get('title') or ('Handoff result' if handoff else 'Work result'))[:160],
        preview=redact((f.get('preview') or '')[:400])[:400] or None,
        truncated=bool(f.get('truncated') or len(f.get('preview') or '')>400),
        outcome=f['stage'], verification_state=f.get('verification'), cleanup_state=f.get('cleanup'),
        delivery_semantics=delivery_semantics(f),
        created_at=f['received_at'], detail_target=target,
        artifacts=[{k:redact(v)[:160] if k=='filename' else v for k,v in a.items() if v is not None}
            for a in (f.get('artifacts') or [])],
        view_state='not_tracked', attention=None,
        _attention_id='att_' + digest([1, 'result_unseen', 'handoff_result' if handoff else 'execution_result', handoff or f['operation_id'], episode])))


def activity_item(raw, server, occurrences):
    item = activity(json.loads(raw), server)
    item['title'] = redact(item['title'])[:160]
    values = json.loads(occurrences or '[]')
    item['attention_refs'] = sorted(o['attention_id'] for o in values)
    # Snoozing/seeing an occurrence changes presentation, never the actual
    # question's pending state. Resolution and authority are canonical facts.
    pending = [o for o in values if o['resolution'] == 'open' and o['freshness'] == 'current']
    if any(o['kind'] in ('native_question_pending', 'native_permission_pending') and o['category'] == 'action_required' for o in pending):
        item['display_state'] = 'awaiting_operator'
        item['evidence_status'] = 'confirmed'
    elif any(o['kind'] == 'question_waiting_for_agent' for o in pending):
        item['display_state'] = 'awaiting_agent'
        item['evidence_status'] = 'confirmed'
    return canonical(item)


def result_attention(raw, occurrence):
    item = json.loads(raw)
    value = json.loads(occurrence) if occurrence else None
    return canonical(result_attention_value(item, value))


def result_attention_value(item, value):
    """The same projection for an already decoded, request-local occurrence."""
    item.pop('_attention_id', None)
    item['attention'] = value
    item['view_state'] = ('seen' if value['seen_state']['seen'] else 'unseen') if value else 'not_tracked'
    return item


class SqliteHomeQueries:
    QUERY_SECONDS = 5.0

    @staticmethod
    def _attention_relations(relation):
        import re
        sql, params = relation
        sql = re.sub(r':([a-zA-Z_][a-zA-Z_0-9]*)', r':att_\1', sql)
        # Canonical policies project authorized source facts. Only partition
        # those occurrences: NULL is never inferred from a missing workspace.
        ctes = '''WITH home_attention_all AS MATERIALIZED (''' + sql + ''' SELECT item FROM filtered),
          home_attention AS MATERIALIZED (SELECT item FROM home_attention_all
            WHERE json_extract(item,'$.workspace_id') IS NOT NULL
              AND (:workspace_id IS NULL OR json_extract(item,'$.workspace_id')=:workspace_id)),
          home_server_attention AS MATERIALIZED (SELECT item FROM home_attention_all
            WHERE json_extract(item,'$.workspace_id') IS NULL)'''
        return ctes, {'att_' + key: value for key, value in params.items()}

    @staticmethod
    def _attention_aggregate(partition, *, page_limit, after=False):
        actionable = (" AND json_extract(item,'$.category')='action_required'"
            " AND (:agent_id IS NULL OR json_extract(item,'$.agent_id')=:agent_id)") if partition == 'home_attention' else ''
        source = f"SELECT item FROM {partition} WHERE json_extract(item,'$.active')=1" + actionable
        cursor = ''' WHERE json_extract(item,'$.priority')<:after_priority OR
          (json_extract(item,'$.priority')=:after_priority AND
           (json_extract(item,'$.first_detected_at')>:after_first OR
            (json_extract(item,'$.first_detected_at')=:after_first AND
             json_extract(item,'$.attention_id')>:after_id)))''' if after else ''
        page = 'SELECT item FROM (' + source + ')' + cursor + '''
          ORDER BY json_extract(item,'$.priority') DESC,json_extract(item,'$.first_detected_at'),
            json_extract(item,'$.attention_id') LIMIT :''' + page_limit
        return '''SELECT json_object('total',COUNT(*),'snapshot_revision',nexus_attention_set_digest_v1(item),
          'next_change_at',(SELECT MIN(json_extract(item,'$.next_change_at')) FROM ''' + partition + '''
            WHERE json_extract(item,'$.next_change_at')>:now),
          'items',json((SELECT json_group_array(json(item)) FROM (''' + page + ''')))) FROM (''' + source + ')'

    def overview(self, uow, *, scope, server_id, now, limits, attention_relation, presentation_version=1):
        """Share the canonical occurrence projection across three Home blocks.

        This is a statement-local materialization, never a stored snapshot or
        temporary table. The service falls back to isolated reads on failure.
        """
        attention_ctes, params = self._attention_relations(attention_relation)
        params.update(server_id=server_id, home_now=now, workspace_id=scope.get('workspace_id'),
            delivery_presentation_version=presentation_version,
            agent_id=scope.get('agent_id'), state=scope.get('state'),
            after_time=None, after_id=None, home_attention_limit=limits['attention']+1,
            home_server_attention_limit=limits['server_attention']+1, now=now)
        fragments = []
        for section in ('work','results'):
            relation = FACTS if section=='work' else RESULTS
            field = 'last_activity_at' if section=='work' else 'created_at'
            params[section+'_limit'] = limits[section]+1
            fragments.append('(' + relation + self._aggregate_sql(field, section+'_limit', as_json=True) + ') AS '+section)
        for name, partition in (('attention','home_attention'),('server_attention','home_server_attention')):
            fragments.append('(' + self._attention_aggregate(partition, page_limit='home_'+name+'_limit') + ') AS '+name)
        sql = attention_ctes + ' SELECT '
        with self.bounded(uow.connection):
            row = uow.connection.execute(sql + ','.join(fragments), params).fetchone()
        result = {}
        for section in ('work','results'):
            result[section] = self._page_result(json.loads(row[section]), section=section, scope=scope,
                now=now, limit=limits[section], after=None)
        for name in ('attention','server_attention'):
            result[name] = json.loads(row[name])
            result[name]['snapshot_revision'] = result[name]['snapshot_revision'] or _SetDigest().finalize()
        return result

    @staticmethod
    def _aggregate_sql(time_field, limit_key='limit', *, as_json=False):
        page = f"""SELECT item FROM filtered WHERE :after_time IS NULL OR
          COALESCE(json_extract(item,'$.{time_field}'),'')<:after_time OR
          (COALESCE(json_extract(item,'$.{time_field}'),'')=:after_time AND json_extract(item,'$.id')>:after_id)
          ORDER BY COALESCE(json_extract(item,'$.{time_field}'),'') DESC,json_extract(item,'$.id') LIMIT :{limit_key}"""
        fields = [ ('total','COUNT(*)'), ('revision','home_digest_v1(item)'),
            ('running',"SUM(COALESCE(json_extract(item,'$.running_count'),0)>0)"),
            ('waiting',"SUM(json_extract(item,'$.display_state') IN ('queued','awaiting_owner','claimed','native_accepted'))"),
            ('tracked',"SUM(json_extract(item,'$.view_state') IN ('seen','unseen'))"),
            ('unseen',"SUM(json_extract(item,'$.view_state')='unseen')"),
            ('items','(SELECT json_group_array(json(item)) FROM ('+page+'))')]
        if as_json:
            return 'SELECT json_object('+','.join("'"+key+"',"+expr for key,expr in fields)+') FROM filtered'
        return 'SELECT '+','.join(expr+' AS '+key for key,expr in fields)+' FROM filtered'

    def attention_page(self, uow, *, relation, limit, scope, now, serverwide=False, after=None):
        from ....domain.home import invalid
        sql, params = self._attention_relations(relation)
        params.update(workspace_id=scope.get('workspace_id'), agent_id=scope.get('agent_id'),
            now=now, home_attention_limit=limit+1)
        if after:
            try:
                priority, first = json.loads(after['key'][0])
                if type(priority) is not int or type(first) is not str:
                    raise ValueError
            except (ValueError, TypeError):
                invalid('Invalid Home attention cursor ordering key.')
            params.update(after_priority=priority, after_first=first, after_id=after['key'][1])
        partition = 'home_server_attention' if serverwide else 'home_attention'
        with self.bounded(uow.connection):
            row = uow.connection.execute(sql + ' ' + self._attention_aggregate(partition,
                page_limit='home_attention_limit', after=after is not None), params).fetchone()
        value = json.loads(row[0])
        value['snapshot_revision'] = value['snapshot_revision'] or _SetDigest().finalize()
        if after and after['revision'] != value['snapshot_revision']:
            raise OktoNexusError(ErrorCode.CONFLICT, 'Home attention changed while paging.',
                dict(reason='HOME_SNAPSHOT_CHANGED'))
        return value

    @contextmanager
    def bounded(self, conn):
        deadline = time.monotonic() + self.QUERY_SECONDS
        conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        conn.create_function('home_activity_v1', 3, activity_item)
        conn.create_function('home_result_v1', 1, result_item)
        conn.create_function('home_result_attention_v1', 2, result_attention)
        conn.create_aggregate('home_digest_v1', 1, _SetDigest)
        try:
            yield
        finally:
            conn.set_progress_handler(None, 0)
            conn.create_function('home_activity_v1', 3, None)
            conn.create_function('home_result_v1', 1, None)
            conn.create_function('home_result_attention_v1', 2, None)
            conn.create_aggregate('home_digest_v1', 1, None)

    def page(self, uow, *, section, scope, server_id, now, limit, after=None, attention_relation=None, presentation_version=1):
        relation = FACTS if section == 'work' else RESULTS if section == 'results' else ACTIVITY
        time_field = 'last_activity_at' if section == 'work' else 'created_at'
        params = dict(server_id=server_id, home_now=now, workspace_id=scope.get('workspace_id'), agent_id=scope.get('agent_id'),
            delivery_presentation_version=presentation_version,
            state=scope.get('state'), limit=limit + 1,
            after_time=after['key'][0] if after else None, after_id=after['key'][1] if after else None)
        if section in ('work', 'results'):
            attention_sql = 'SELECT NULL AS item WHERE 0'
            if attention_relation:
                attention_ctes, attention_params = self._attention_relations(attention_relation)
                params.update(attention_params)
            else:
                attention_ctes = 'WITH home_attention AS MATERIALIZED (' + attention_sql + ')'
            relation = attention_ctes + ',' + relation.lstrip()[4:]
        with self.bounded(uow.connection):
            row = uow.connection.execute(relation + self._aggregate_sql(time_field), params).fetchone()
        return self._page_result(row, section=section, scope=scope, now=now, limit=limit, after=after)

    def _page_result(self, row, *, section, scope, now, limit, after):
        time_field = 'last_activity_at' if section == 'work' else 'created_at'
        revision = row['revision'] or _SetDigest().finalize()
        if after and after['revision'] != revision:
            raise OktoNexusError(ErrorCode.CONFLICT, 'Home changed while paging. Refresh the section.',
                dict(reason='HOME_SNAPSHOT_CHANGED'))
        items = json.loads(row['items']) if isinstance(row['items'],str) else row['items']
        more = len(items) > limit
        items = items[:limit]
        cursor = encode_cursor(section, scope, revision, [items[-1].get(time_field) or '', items[-1]['id']]) if more else None
        return dict(status='ready', as_of=now, next_refresh_at=(instant(now) + timedelta(seconds=15)).isoformat(),
            items=items, total=row['total'], total_is_exact=True, has_more=more, next_cursor=cursor, revision=revision), dict(
                running=row['running'] or 0, waiting=row['waiting'] or 0,
                new_results=(row['unseen'] or 0) if (row['tracked'] or 0)==row['total'] else None)

    def agents(self, uow, *, scope, now, limit, clock, config, after=None):
        with self.bounded(uow.connection):
            return self._agents(uow, scope=scope, now=now, limit=limit, clock=clock, config=config, after=after)

    def _agents(self, uow, *, scope, now, limit, clock, config, after=None):
        from ....application.observability import activity_presence
        from types import SimpleNamespace
        clock = SimpleNamespace(now_epoch=lambda: instant(now).timestamp())
        sql = """WITH membership AS (
          SELECT agent_id,workspace_id FROM sessions UNION SELECT agent_id,workspace_id FROM agent_endpoints
          UNION SELECT from_agent_id,workspace_id FROM handoffs UNION SELECT claimed_by,workspace_id FROM handoffs WHERE claimed_by IS NOT NULL
          UNION SELECT json_extract(target,'$.agent_id'),workspace_id FROM handoffs
            WHERE json_extract(target,'$.strategy') IN ('direct','direct_with_fallback')
              AND json_type(target,'$.agent_id')='text'
          UNION SELECT from_agent_id,workspace_id FROM messages
          UNION SELECT d.recipient_agent_id,m.workspace_id FROM message_deliveries d JOIN messages m USING(message_id)
        ), visible AS MATERIALIZED (
          SELECT a.agent_id,a.is_active,a.last_seen_at,
           (SELECT json_group_array(workspace_id) FROM membership m WHERE m.agent_id=a.agent_id) AS workspaces,
           MAX(CASE WHEN s.status='active' THEN s.last_heartbeat_at END) AS heartbeat,
           MAX(CASE WHEN s.status='active' THEN 1 ELSE 0 END) AS active_session
          FROM agents a LEFT JOIN sessions s ON s.agent_id=a.agent_id AND (:workspace_id IS NULL OR s.workspace_id=:workspace_id)
          WHERE a.agent_id<>'operator' AND (:agent_id IS NULL OR a.agent_id=:agent_id) AND (:workspace_id IS NULL OR EXISTS(
            SELECT 1 FROM membership m WHERE m.agent_id=a.agent_id AND m.workspace_id=:workspace_id))
          GROUP BY a.agent_id
        ) """
        params = dict(workspace_id=scope.get('workspace_id'), agent_id=scope.get('agent_id'), limit=limit + 1,
            after=after['key'][1] if after else '')
        aggregate = uow.connection.execute(sql + "SELECT COUNT(*) AS count,home_digest_v1(json_array(agent_id,is_active,workspaces)) AS revision FROM visible", params).fetchone()
        count, revision = aggregate['count'], aggregate['revision'] or _SetDigest().finalize()
        if after and after['revision'] != revision:
            raise OktoNexusError(ErrorCode.CONFLICT, 'Home agent membership changed.', dict(reason='HOME_SNAPSHOT_CHANGED'))
        rows = uow.connection.execute(sql + 'SELECT * FROM visible WHERE agent_id>:after ORDER BY agent_id LIMIT :limit', params).fetchall()
        items = [dict(agent_id=r['agent_id'], name=r['agent_id'], workspace_ids=json.loads(r['workspaces']),
            presence=activity_presence(clock, config, has_active_session=bool(r['active_session']),
                last_heartbeat_at=r['heartbeat'], last_seen_at=r['last_seen_at']) if r['is_active'] else 'offline',
            connectivity='unknown', activity='not_reported') for r in rows[:limit]]
        return dict(status='ready', as_of=now, next_refresh_at=(instant(now) + timedelta(seconds=15)).isoformat(),
            items=items, total=count, total_is_exact=True, revision=revision,
            has_more=len(rows)>limit, next_cursor=encode_cursor('agents', scope, revision, ['', items[-1]['agent_id']]) if len(rows)>limit else None)

    def external(self, uow, *, scope, now, config, limit, observations, after=None):
        with self.bounded(uow.connection):
            return self._external(uow, scope=scope, now=now, config=config, limit=limit, observations=observations, after=after)

    def _external(self, uow, *, scope, now, config, limit, observations, after=None):
        params = dict(workspace=scope.get('workspace_id'), agent=scope.get('agent_id'))
        clause = ' FROM observation_instances i JOIN observation_sources s USING(source_id) WHERE (:workspace IS NULL OR i.workspace_id=:workspace) AND (:agent IS NULL OR s.agent_id=:agent)'
        aggregate = uow.connection.execute('SELECT COUNT(*) AS count,home_digest_v1(json_array(i.observed_instance_id,i.generation,i.workspace_id,s.revision,s.enabled,s.revoked_at)) AS revision' + clause, params).fetchone()
        revision = aggregate['revision'] or _SetDigest().finalize()
        if after and after['revision'] != revision:
            raise OktoNexusError(ErrorCode.CONFLICT, 'Home observation membership changed.', dict(reason='HOME_SNAPSHOT_CHANGED'))
        selected = observations.repo.list_current(uow, agent_id=scope.get('agent_id'), workspace_id=scope.get('workspace_id'),
            after=after['key'][1] if after else None, limit=limit+1)
        items = observations._project_current(uow, selected[:limit], now, config)
        more = len(selected)>limit
        return dict(status='ready', as_of=now, items=items, total=aggregate['count'], total_is_exact=True,
            revision=revision, has_more=more,
            next_cursor=encode_cursor('external', scope, revision, ['', items[-1]['observed_instance_id']]) if more else None,
            next_refresh_at=observations._refresh(items, now)['next_refresh_at'])

    def target(self, uow, target):
        kind = target['kind']
        if kind == 'handoff':
            sql = 'SELECT workspace_id,status,claim_epoch,updated_at,claimed_by AS agent_id FROM handoffs WHERE handoff_id=:handoff_id'
        elif kind == 'message':
            sql = 'SELECT workspace_id,message_id,from_agent_id AS agent_id,created_at FROM messages WHERE message_id=:message_id'
        elif kind == 'approval':
            sql = 'SELECT workspace_id,approval_id,status,created_at,decided_at FROM approvals WHERE approval_id=:approval_id'
        elif kind == 'session':
            # Historical scope belongs to the admitted opening and session, not
            # a binding's current endpoint/workspace after reconfiguration.
            # This is read metadata only and never establishes current control.
            sql = '''SELECT s.server_id,s.executor_id,s.workspace_id,s.session_id,s.binding_id,
              s.workspace_binding_id,o.subject_agent_id AS agent_id,s.lifecycle_state,s.owner_generation,s.lease_state,s.stream_epoch,
              json_extract(o.expected_revisions_json,'$.binding_revision') AS binding_revision,
              w.revision AS workspace_binding_revision
              FROM execution_sessions s
              JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id
                AND o.session_id=s.session_id AND o.operation_id=s.open_operation_id AND o.action='runtime.open'
              JOIN execution_workspace_bindings w ON w.server_id=s.server_id AND w.executor_id=s.executor_id
                AND w.workspace_binding_id=s.workspace_binding_id AND w.workspace_id=s.workspace_id
              WHERE s.server_id=:server_id AND s.executor_id=:executor_id AND s.session_id=:session_id
                AND o.workspace_id=s.workspace_id AND o.binding_id=s.binding_id'''
        elif kind == 'connection':
            sql = '''SELECT b.server_id,b.executor_id,w.workspace_id,b.binding_id,b.workspace_binding_id,
              ep.agent_id,b.binding_revision,w.revision AS workspace_binding_revision
              FROM execution_bindings b
              JOIN execution_workspace_bindings w ON w.server_id=b.server_id AND w.executor_id=b.executor_id
                AND w.workspace_binding_id=b.workspace_binding_id
              JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id AND ep.workspace_id=w.workspace_id
              WHERE b.server_id=:server_id AND b.executor_id=:executor_id
                AND b.binding_id=:binding_id AND ep.agent_id=:agent_id'''
        elif kind in ('execution', 'result'):
            sql = '''SELECT o.workspace_id,o.subject_agent_id AS agent_id,o.admission_state,s.lifecycle_state,
              s.owner_generation,COALESCE(r.receipt_revision,0) AS receipt_revision
              FROM execution_operations o JOIN execution_sessions s USING(server_id,executor_id,session_id)
              LEFT JOIN execution_receipts r USING(server_id,executor_id,operation_id)
              WHERE o.server_id=:server_id AND o.executor_id=:executor_id AND o.operation_id=:operation_id
                AND o.session_id=:session_id ORDER BY r.receipt_revision DESC LIMIT 1'''
        else:
            sql = '''SELECT i.workspace_id,i.observed_instance_id,i.generation,s.agent_id,s.revision,s.enabled,s.revoked_at
              FROM observation_instances i JOIN observation_sources s USING(source_id)
              WHERE i.observed_instance_id=:observed_instance_id AND i.source_id=:source_id AND i.generation=:generation'''
        row = uow.connection.execute(sql, target).fetchone()
        return dict(row) if row else None


# Feed uses a closed list of business event names and never selects payload.
ACTIVITY = """WITH facts AS MATERIALIZED (
 SELECT event_id,workspace_id,type,actor_agent_id,created_at FROM events
 WHERE type IN ('handoff.created','handoff.claimed','handoff.completed','handoff.rejected',
  'handoff.cancelled','handoff.expired','handoff.recovered','handoff.verification_requested',
  'handoff.verification_failed','handoff.unblocked','handoff.dependency_failed',
  'message.created','approval.requested','approval.granted','approval.denied')
  AND (:workspace_id IS NULL OR workspace_id=:workspace_id)
  AND (:agent_id IS NULL OR actor_agent_id=:agent_id)
), filtered AS MATERIALIZED (
 SELECT json_object('id',CAST(event_id AS TEXT),'workspace_id',workspace_id,'kind',type,
   'agent_id',actor_agent_id,'created_at',created_at,'label',type) AS item FROM facts)
"""
