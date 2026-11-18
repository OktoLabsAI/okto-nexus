
WITH links AS MATERIALIZED (
 SELECT server_id,executor_id,operation_id,domain_operation_id FROM execution_domain_deliveries
 UNION SELECT server_id,executor_id,operation_id,domain_operation_id FROM execution_delivery_attempt_history
), scoped_ops AS MATERIALIZED (
 SELECT o.server_id,o.executor_id,o.operation_id,o.session_id,o.workspace_id,o.subject_agent_id,
   o.actor_agent_id,o.admission_state,o.created_at,r.stage,r.received_at,r.receipt_revision,s.lifecycle_state,
   CASE WHEN s.lifecycle_state IN ('READY','ACTIVE') AND s.lease_state='ACTIVE'
     AND r.stage NOT IN ('SUCCEEDED','FAILED','CANCELLED','OUTCOME_UNKNOWN','REFUSED_BEFORE_EFFECT')
     AND json_extract(o.expected_revisions_json,'$.session_owner_generation')=s.owner_generation
     AND EXISTS(SELECT 1 FROM execution_event_ingress e JOIN execution_event_watermarks w
       USING(server_id,executor_id,session_id,stream_epoch)
       WHERE e.server_id=o.server_id AND e.executor_id=o.executor_id AND e.session_id=o.session_id
         AND e.stream_epoch=s.stream_epoch AND e.sequence<=w.projected_through AND w.gap_state='none'
         AND json_extract(e.payload_json,'$.operation_id')=o.operation_id
         AND json_extract(e.payload_json,'$.payload.delivery_phase') IN ('started','progress'))
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
    FILTER(WHERE position<=20) AS runtime_refs
 FROM ranked GROUP BY group_key
), parents AS MATERIALIZED (
 SELECT 'handoff' AS kind,h.handoff_id AS source_id,h.workspace_id,h.status,h.created_at AS created,
  h.updated_at AS changed,substr(t.title,1,160) AS title,
  CASE WHEN t.title IS NULL OR t.title='' THEN 'fallback' ELSE 'canonical_title' END AS title_origin,
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
  substr(m.subject,1,160),CASE WHEN m.subject IS NULL OR m.subject='' THEN 'fallback' ELSE 'message_subject' END,
  m.from_agent_id,d.recipient_agent_id,m.message_id,NULL,NULL,json_array('conversation_turn',d.operation_id),0,0
 FROM delivery_outbox d JOIN messages m ON m.message_id=d.message_id
 WHERE (:workspace_id IS NULL OR d.workspace_id=:workspace_id)
   AND NOT EXISTS(SELECT 1 FROM runtime_handoff_bindings b WHERE b.operation_id=d.operation_id)
 UNION ALL
 SELECT 'direct_operation',o.operation_id,o.workspace_id,o.admission_state,o.created_at,NULL,NULL,'fallback',
  o.actor_agent_id,o.subject_agent_id,NULL,o.executor_id,o.session_id,o.group_key,0,0
 FROM scoped_ops o WHERE o.domain_operation_id IS NULL
), facts AS MATERIALIZED (
 SELECT json_object('kind',p.kind,'source_id',p.source_id,'workspace_id',p.workspace_id,'status',p.status,
  'created',p.created,'changed',p.changed,'title',p.title,'title_origin',p.title_origin,
  'agent_ids',json_array(p.sender,p.recipient),'message_id',p.message_id,'executor_id',p.executor_id,
  'session_id',p.session_id,'blocked',p.blocked,'claim_expired',p.claim_expired,'running',COALESCE(g.running,0),
  'running_since',g.running_since,'latest',g.latest,'attempt_count',COALESCE(g.attempts,0),
  'runtime_refs',json(COALESCE(g.runtime_refs,'[]')),'stage',last.stage,'receipt_at',last.received_at,
  'cleanup',COALESCE(last.cleanup,0)) AS fact
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
    AND json_extract(item,'$.session_id')=json_extract(ref.value,'$.session_id')))))) AS item FROM facts),
filtered AS MATERIALIZED (SELECT item FROM projected WHERE
 (:state IS NOT NULL AND (:state='all' OR json_extract(item,'$.display_state')=:state)) OR
 (:state IS NULL AND json_extract(item,'$.display_state') NOT IN ('completed','turn_completed','failed','cancelled')))
