"""Operator troubleshooting read model. Never returns native prompts or tool input."""
import json
import re
from datetime import datetime

from ..errors import ErrorCode, OktoNexusError


def diagnostic_text(value):
    if not isinstance(value, (str, int, float, bool)):
        return None
    text = str(value)
    text = re.sub(r'(?i)(bearer\s+)[\w.\-]+', r'\1[redacted]', text)
    text = re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|password|secret|authorization)\s*[=:]\s*)[^\s,;]+', r'\1[redacted]', text)
    text = re.sub(r'\b(?:sk-|nxt4_|nxk_)[A-Za-z0-9_\-]+', '[redacted]', text)
    return text[:2000]


def read_execution_log(factory, *, workspace_id=None, severity=None, agent_id=None,
                       adapter_id=None, since=None, until=None, offset=0, limit=100):
    if severity not in (None, 'info', 'warning', 'error') or offset < 0 or not 1 <= limit <= 200:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid execution log filter.', {})
    dates = []
    for value in (since, until):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None
            if parsed and parsed.tzinfo is None:
                raise ValueError()
            dates.append(parsed)
        except ValueError as exc:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Use a timestamp with timezone.', {}) from exc
    if all(dates) and dates[0] > dates[1]:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Start must precede end.', {})
    # Read durable facts, including failure before a native session can emit events.
    # Dispatch has no update timestamp: its timestamp is explicitly operation creation.
    query = """
    WITH log AS (
      SELECT 'recovery:'||r.id id,r.created_at timestamp,'runtime recovery' source,
        CASE WHEN r.code='RECOVERY_READY' THEN 'info' ELSE 'warning' END severity,
        NULL agent_id,NULL workspace_id,NULL adapter_id,NULL endpoint_id,NULL session_id,NULL operation_id,
        r.executor_id,'runtime.recover' action,r.code,json_object('message',r.message) detail FROM runtime_recovery_events r
      UNION ALL
      SELECT 'pending:'||p.delivery_id,p.created_at,'runtime recovery',CASE WHEN p.status='attention' THEN 'error' ELSE 'warning' END,
        d.recipient_agent_id,m.workspace_id,NULL,NULL,NULL,NULL,NULL,'message.wait',
        CASE WHEN p.status='attention' THEN 'RECOVERY_ATTENTION_REQUIRED' ELSE 'WAITING_FOR_RUNTIME_RECOVERY' END,
        json_object('message',coalesce(p.reason,'Waiting for runtime recovery'))
      FROM runtime_pending_deliveries p JOIN message_deliveries d USING(delivery_id) JOIN messages m USING(message_id)
      WHERE p.status IN ('waiting','attention')
      UNION ALL
      SELECT 'receipt:'||r.server_id||':'||r.executor_id||':'||r.operation_id||':'||r.receipt_revision id,
        r.received_at timestamp, 'receipt' source,
        CASE WHEN r.error_code IS NOT NULL OR r.stage='FAILED' THEN 'error'
             WHEN r.stage IN ('CANCELLED','OUTCOME_UNKNOWN') THEN 'warning' ELSE 'info' END severity,
        o.subject_agent_id agent_id,o.workspace_id,ep.adapter_id,b.endpoint_id,
        o.session_id,o.operation_id,o.executor_id,o.action,
        coalesce(r.error_code,r.stage) code,
        json_object('stage',r.stage,'possible_effect',r.possible_effect,'retry_safe',r.retry_safe) detail
      FROM execution_receipts r JOIN execution_operations o USING(server_id,executor_id,operation_id)
      JOIN execution_installation i ON i.server_id=o.server_id
      LEFT JOIN execution_bindings b ON b.server_id=o.server_id AND b.executor_id=o.executor_id AND b.binding_id=o.binding_id
      LEFT JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
      UNION ALL
      SELECT 'dispatch:'||o.server_id||':'||o.executor_id||':'||o.operation_id,o.created_at,'dispatch snapshot',
        CASE WHEN d.dispatch_state='RECONCILING' THEN 'warning' ELSE 'error' END,
        o.subject_agent_id,o.workspace_id,ep.adapter_id,b.endpoint_id,o.session_id,o.operation_id,o.executor_id,o.action,
        coalesce(json_extract(d.last_error,'$.code'),d.dispatch_state),d.last_error
      FROM execution_dispatch_outbox d JOIN execution_operations o USING(server_id,executor_id,operation_id)
      JOIN execution_installation i ON i.server_id=o.server_id
      LEFT JOIN execution_bindings b ON b.server_id=o.server_id AND b.executor_id=o.executor_id AND b.binding_id=o.binding_id
      LEFT JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
      WHERE d.last_error IS NOT NULL AND json_valid(d.last_error)
      UNION ALL
      SELECT 'event:'||e.server_id||':'||e.executor_id||':'||e.session_id||':'||e.stream_epoch||':'||e.sequence,
        e.received_at,'runtime event',
        CASE WHEN e.event_type='error' THEN 'error' WHEN e.event_type='input_request' THEN 'warning' ELSE 'info' END,
        ep.agent_id,s.workspace_id,ep.adapter_id,b.endpoint_id,e.session_id,
        json_extract(e.payload_json,'$.operation_id'),e.executor_id,e.event_type,
        coalesce(json_extract(e.payload_json,'$.native_type'),e.event_type),json_extract(e.payload_json,'$.payload')
      FROM execution_event_ingress e JOIN execution_sessions s USING(server_id,executor_id,session_id)
      JOIN execution_installation i ON i.server_id=e.server_id
      JOIN execution_event_watermarks w USING(server_id,executor_id,session_id,stream_epoch)
      LEFT JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id AND b.binding_id=s.binding_id
      LEFT JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
      WHERE e.event_type IN ('error','lifecycle','turn_state','input_request') AND e.sequence<=w.committed_contiguous
      UNION ALL
      SELECT 'access:'||a.audit_id,a.created_at,'authorization',
        CASE WHEN a.decision='deny' THEN 'warning' ELSE 'info' END,
        coalesce(ep.agent_id,a.actor_agent_id),ep.workspace_id,ep.adapter_id,a.endpoint_id,a.session_id,NULL,NULL,
        a.action,a.decision,json_object('actor',a.actor_agent_id,'decision',a.decision)
      FROM runtime_access_audit a LEFT JOIN agent_endpoints ep ON ep.endpoint_id=a.endpoint_id
      UNION ALL
      SELECT 'routing:'||d.delivery_id||':'||ep.endpoint_id,d.created_at,'routing snapshot','warning',
        d.recipient_agent_id,m.workspace_id,ep.adapter_id,ep.endpoint_id,NULL,NULL,NULL,'message.route',
        'AUTOMATIC_REPLY_DISABLED',
        json_object('message','Message remains unread. Automatic replies are currently disabled for this connection. This is a legacy connection state. Reopen Connections and finish setup to update it. Timestamp is message creation; this is current routing state.')
      FROM message_deliveries d JOIN messages m ON m.message_id=d.message_id
      JOIN agent_endpoints ep ON ep.agent_id=d.recipient_agent_id AND ep.workspace_id=m.workspace_id
      WHERE d.status='unread' AND ep.protocol='nxl-r4' AND ep.enabled=1
        AND ep.activation_state='approved' AND ep.response_policy='explicit'
        AND NOT EXISTS (SELECT 1 FROM delivery_outbox o WHERE o.delivery_id=d.delivery_id)
        AND NOT EXISTS (SELECT 1 FROM agent_endpoints ready WHERE ready.agent_id=ep.agent_id
          AND ready.workspace_id=ep.workspace_id AND ready.enabled=1 AND ready.activation_state='approved'
          AND ready.response_policy='conversation' AND ready.consumption='exclusive')
    ) SELECT * FROM log WHERE 1=1
    """
    params = []
    for column, value in (('workspace_id', workspace_id), ('severity', severity), ('agent_id', agent_id), ('adapter_id', adapter_id)):
        if value:
            if column in ('workspace_id', 'agent_id', 'adapter_id'):
                # Executor recovery affects every connection on that host;
                # keep it visible when filtering one affected connection.
                query += f" AND ({column}=? OR (source='runtime recovery' AND log.agent_id IS NULL " \
                    f"AND EXISTS (SELECT 1 FROM execution_bindings b JOIN agent_endpoints ep USING(endpoint_id) " \
                    f"WHERE b.executor_id=log.executor_id AND ep.{column}=?)))"
                params.extend((value, value))
            else:
                query += f' AND {column}=?'
                params.append(value)
    for operator, value in (('>=', since), ('<=', until)):
        if value:
            query += f' AND julianday(timestamp){operator}julianday(?)'
            params.append(value)
    query += ' ORDER BY julianday(timestamp) DESC,id DESC LIMIT ? OFFSET ?'
    with factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute(query, (*params, limit + 1, offset)).fetchall()
    items = []
    for row in rows[:limit]:
        item = dict(row)
        raw = json.loads(item.pop('detail') or '{}')
        if not isinstance(raw, dict):
            raw = {}
        # Strict projection excludes stdin, environment, full native frames and tool arguments.
        fields = ('code', 'message', 'stage', 'status', 'state', 'exit_code', 'possible_effect',
                  'retry_safe', 'actor', 'decision')
        item['details'] = {key: diagnostic_text(raw[key]) for key in fields if key in raw and diagnostic_text(raw[key]) is not None}
        item['code'] = diagnostic_text(item['code'])
        items.append(item)
    return {'items': items, 'has_more': len(rows) > limit, 'next_offset': offset + len(items)}
