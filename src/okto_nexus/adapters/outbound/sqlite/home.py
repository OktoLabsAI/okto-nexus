"""Bounded HOME read relations. No domain writes, host calls or transcript reads."""
from contextlib import contextmanager
from datetime import timedelta
import json
import time

from ....domain.attention import canonical, digest, instant
from ....domain.home import activity, encode_cursor
from ....errors import ErrorCode, OktoNexusError
from ..harness.event_journal import redact
from .attention import _SetDigest


# Current and historic links are deduplicated before joining receipts. A claim's
# operations are attached only to that epoch, never to a later owner of the work.
FACTS = """
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
  json_extract(item,'$.source_type')=CASE json_extract(fact,'$.kind') WHEN 'handoff' THEN 'handoff' WHEN 'conversation_turn' THEN 'delivery_operation' ELSE 'execution_operation' END)
 OR (json_extract(item,'$.source_type') IN ('execution_native_request','execution_operation','execution_result','handoff_result') AND EXISTS(SELECT 1 FROM json_each(fact,'$.runtime_refs') ref
  WHERE json_extract(item,'$.operation_id')=json_extract(ref.value,'$.operation_id')
    AND json_extract(item,'$.executor_id')=json_extract(ref.value,'$.executor_id')
    AND json_extract(item,'$.session_id')=json_extract(ref.value,'$.session_id')))))) AS item FROM facts),
filtered AS MATERIALIZED (SELECT item FROM projected WHERE
 (:state IS NOT NULL AND (:state='all' OR json_extract(item,'$.display_state')=:state)) OR
 (:state IS NULL AND json_extract(item,'$.display_state') NOT IN ('completed','turn_completed','failed','cancelled')))
"""


RESULTS = """
WITH links AS MATERIALIZED (
 SELECT server_id,executor_id,operation_id,domain_operation_id FROM execution_domain_deliveries
 UNION SELECT server_id,executor_id,operation_id,domain_operation_id FROM execution_delivery_attempt_history
), native AS MATERIALIZED (
 SELECT o.server_id,o.executor_id,o.operation_id,o.session_id,o.workspace_id,o.subject_agent_id,
  r.stage,r.received_at,r.receipt_revision,x.stream_epoch,x.terminal_sequence,x.captured_at,
  CASE WHEN x.terminal_sequence IS NOT NULL THEN substr(x.output_text,1,401) END AS preview,
  x.output_truncated,
  (SELECT json_group_array(json_object('artifact_id',a.artifact_id,'filename',substr(a.name,1,160),'media_type',a.content_type))
   FROM runtime_results rr JOIN artifacts a ON a.artifact_id=rr.output_artifact_id
   WHERE rr.canonical_server_id=o.server_id AND rr.canonical_executor_id=o.executor_id
    AND rr.canonical_operation_id=o.operation_id AND a.workspace_id=o.workspace_id) AS artifacts,
  CASE WHEN k.state='REQUESTED' THEN 'pending' END AS cleanup,
  b.handoff_id,b.claim_epoch, h.claim_epoch AS current_epoch,h.status AS handoff_status,
  substr(t.title,1,160) AS title
 FROM execution_operations o JOIN execution_receipts r USING(server_id,executor_id,operation_id)
 LEFT JOIN execution_results x USING(server_id,executor_id,operation_id)
 LEFT JOIN execution_sessions s USING(server_id,executor_id,session_id)
 LEFT JOIN execution_session_containment k ON k.server_id=s.server_id AND k.executor_id=s.executor_id
  AND k.session_id=s.session_id AND k.owner_generation=s.owner_generation
 LEFT JOIN links l ON l.server_id=o.server_id AND l.executor_id=o.executor_id AND l.operation_id=o.operation_id
 LEFT JOIN runtime_handoff_bindings b ON b.operation_id=l.domain_operation_id
 LEFT JOIN handoffs h ON h.handoff_id=b.handoff_id
 LEFT JOIN tasks t ON t.task_id=h.task_id AND t.workspace_id=h.workspace_id
 WHERE o.server_id=:server_id AND o.action='turn.submit' AND r.stage IN ('SUCCEEDED','FAILED','CANCELLED')
  AND r.receipt_revision=(SELECT MAX(rr.receipt_revision) FROM execution_receipts rr
   WHERE rr.server_id=o.server_id AND rr.executor_id=o.executor_id AND rr.operation_id=o.operation_id)
  AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
  AND (:agent_id IS NULL OR o.subject_agent_id=:agent_id)
), ranked AS MATERIALIZED (
 SELECT *,ROW_NUMBER() OVER(PARTITION BY
  CASE WHEN handoff_id IS NOT NULL THEN json_array('handoff',handoff_id,claim_epoch)
       ELSE json_array('execution',server_id,executor_id,operation_id) END
  ORDER BY received_at DESC,operation_id DESC) AS position FROM native
), facts AS MATERIALIZED (
 SELECT json_object('server_id',server_id,'executor_id',executor_id,'session_id',session_id,'operation_id',operation_id,
  'workspace_id',workspace_id,'agent_id',subject_agent_id,'stage',stage,'received_at',received_at,'title',title,
  'revision',receipt_revision,'cleanup',cleanup,'handoff_id',handoff_id,'claim_epoch',claim_epoch,
  'stream_epoch',stream_epoch,'terminal_sequence',terminal_sequence,'preview',preview,
  'truncated',output_truncated,'artifacts',json(artifacts),
  'verification',CASE WHEN claim_epoch=current_epoch THEN handoff_status ELSE 'historical_claim' END) AS fact
 FROM ranked WHERE position=1
 UNION ALL
 SELECT json_object('server_id',:server_id,'workspace_id',h.workspace_id,'agent_id',COALESCE(h.claimed_by,h.from_agent_id),
  'handoff_id',h.handoff_id,'claim_epoch',h.claim_epoch,'stage',h.status,'verification',h.status,
  'received_at',COALESCE(h.updated_at,h.created_at),'revision',h.claim_epoch,
  'preview',substr(h.result,1,401),'title',substr(t.title,1,160))
 FROM handoffs h LEFT JOIN tasks t ON t.task_id=h.task_id AND t.workspace_id=h.workspace_id
 WHERE h.status IN ('COMPLETED','REJECTED')
  AND (:workspace_id IS NULL OR h.workspace_id=:workspace_id)
  AND (:agent_id IS NULL OR COALESCE(h.claimed_by,h.from_agent_id)=:agent_id)
  AND NOT EXISTS(SELECT 1 FROM native n WHERE n.handoff_id=h.handoff_id AND n.claim_epoch=h.claim_epoch)
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
    item.pop('_attention_id', None)
    value = json.loads(occurrence) if occurrence else None
    item['attention'] = value
    item['view_state'] = ('seen' if value['seen_state']['seen'] else 'unseen') if value else 'not_tracked'
    return canonical(item)


class SqliteHomeQueries:
    QUERY_SECONDS = 5.0

    def overview(self, uow, *, scope, server_id, now, limits, attention_relation):
        """Share the canonical occurrence projection across three Home blocks.

        This is a statement-local materialization, never a stored snapshot or
        temporary table. The service falls back to isolated reads on failure.
        """
        import re
        attention_sql, attention_params = attention_relation
        attention_sql = re.sub(r':([a-zA-Z_][a-zA-Z_0-9]*)', r':att_\1', attention_sql)
        params = {'att_' + key: value for key, value in attention_params.items()}
        params.update(server_id=server_id, home_now=now, workspace_id=scope.get('workspace_id'),
            agent_id=scope.get('agent_id'), state=scope.get('state'),
            after_time=None, after_id=None, home_attention_limit=limits['attention']+1, now=now)
        fragments = []
        for section in ('work','results'):
            relation = FACTS if section=='work' else RESULTS
            field = 'last_activity_at' if section=='work' else 'created_at'
            params[section+'_limit'] = limits[section]+1
            fragments.append('(' + relation + self._aggregate_sql(field, section+'_limit', as_json=True) + ') AS '+section)
        fragments.append('''(SELECT json_object('total',COUNT(*),'snapshot_revision',nexus_attention_set_digest_v1(item),
            'next_change_at',(SELECT MIN(json_extract(item,'$.next_change_at')) FROM home_attention WHERE json_extract(item,'$.next_change_at')>:now),
            'items',json((SELECT json_group_array(json(item)) FROM (SELECT item FROM home_actionable
              ORDER BY json_extract(item,'$.priority') DESC,json_extract(item,'$.first_detected_at'),json_extract(item,'$.attention_id')
              LIMIT :home_attention_limit)))) FROM home_actionable) AS attention''')
        sql = 'WITH home_attention AS MATERIALIZED ('+attention_sql+' SELECT item FROM filtered), home_actionable AS MATERIALIZED ('
        sql += "SELECT item FROM home_attention WHERE json_extract(item,'$.active')=1 AND json_extract(item,'$.category')='action_required') SELECT "
        with self.bounded(uow.connection):
            row = uow.connection.execute(sql + ','.join(fragments), params).fetchone()
        result = {}
        for section in ('work','results'):
            result[section] = self._page_result(json.loads(row[section]), section=section, scope=scope,
                now=now, limit=limits[section], after=None)
        result['attention'] = json.loads(row['attention'])
        result['attention']['snapshot_revision'] = result['attention']['snapshot_revision'] or _SetDigest().finalize()
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

    def attention_page(self, uow, *, relation, limit):
        sql, params = relation
        params = dict(params, home_attention_limit=limit+1)
        sql += ", home_actionable AS MATERIALIZED (SELECT item FROM filtered WHERE json_extract(item,'$.active')=1 AND json_extract(item,'$.category')='action_required') "
        row = uow.connection.execute(sql + '''SELECT COUNT(*) AS total,
            nexus_attention_set_digest_v1(item) AS revision,
            (SELECT MIN(json_extract(item,'$.next_change_at')) FROM viewing
             WHERE json_extract(item,'$.next_change_at')>:now) AS next_change_at,
            (SELECT json_group_array(json(item)) FROM (SELECT item FROM home_actionable
             ORDER BY json_extract(item,'$.priority') DESC,json_extract(item,'$.first_detected_at'),
               json_extract(item,'$.attention_id') LIMIT :home_attention_limit)) AS items
            FROM home_actionable''', params).fetchone()
        return dict(total=row['total'], snapshot_revision=row['revision'] or _SetDigest().finalize(),
            next_change_at=row['next_change_at'], items=json.loads(row['items']))

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

    def page(self, uow, *, section, scope, server_id, now, limit, after=None, attention_relation=None):
        relation = FACTS if section == 'work' else RESULTS if section == 'results' else ACTIVITY
        time_field = 'last_activity_at' if section == 'work' else 'created_at'
        params = dict(server_id=server_id, home_now=now, workspace_id=scope.get('workspace_id'), agent_id=scope.get('agent_id'),
            state=scope.get('state'), limit=limit + 1,
            after_time=after['key'][0] if after else None, after_id=after['key'][1] if after else None)
        if section in ('work', 'results'):
            attention_sql = 'SELECT NULL AS item WHERE 0'
            if attention_relation:
                attention_sql, attention_params = attention_relation
                # Attention's parameters are namespaced to avoid its state and
                # category filters colliding with the Home work-state filter.
                import re
                attention_sql = re.sub(r':([a-zA-Z_][a-zA-Z_0-9]*)', r':att_\1', attention_sql)
                params.update({'att_' + key: value for key, value in attention_params.items()})
                attention_sql += ' SELECT item FROM filtered'
            relation = 'WITH home_attention AS MATERIALIZED (' + attention_sql + '),' + relation.lstrip()[4:]
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
