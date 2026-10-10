"""Server-owned failure replies, restricted to the original authenticated caller.

This is not an agent tool or an arbitrary message bypass. Recipient, workspace,
parent and body derive exclusively from the durable admitted call and outcome.
Notification insertion, inbox delivery and event append commit atomically.
"""
import hashlib
import json
from ..domain.messages import MESSAGE_STREAM, MESSAGE_CREATED_TYPE


def publish_errors(deps, messages):
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        rows = conn.execute('SELECT c.call_id,c.caller_id,c.agent_id,c.outcome_json,d.workspace_id,d.message_id,m.channel_id '
            'FROM one_shot_calls c JOIN delivery_outbox d ON d.operation_id=c.call_id '
            'JOIN messages m ON m.message_id=d.message_id '
            "WHERE c.state IN ('FAILED','CANCELLED') AND c.outcome_json IS NOT NULL AND c.notification_message_id IS NULL "
            'AND c.caller_id=m.from_agent_id AND c.agent_id=d.recipient_agent_id ORDER BY c.enqueued_at LIMIT 32').fetchall()
        for row in rows:
            outcome = json.loads(row['outcome_json'])
            error = outcome['error']
            identity = hashlib.sha256(row['call_id'].encode()).hexdigest()
            message_id = 'msg_one_shot_' + identity
            target = dict(strategy='direct', agent_id=row['caller_id'])
            now = deps.clock.now_iso()
            body = error['code'] + ': ' + error['message'] + '\n\n' + json.dumps(outcome, ensure_ascii=False, indent=2)
            message = messages._messages.create(uow, message_id=message_id, workspace_id=row['workspace_id'],
                from_agent_id=row['agent_id'], channel_id=row['channel_id'], from_session_id=None,
                target=json.dumps(target), subject='Nexus one-shot error', body=body, artifacts=[],
                parent_message_id=row['message_id'], trace_id=None, created_at=now)
            messages._deliveries.create(uow, delivery_id='del_one_shot_' + identity, message_id=message_id,
                recipient_agent_id=row['caller_id'], status='unread', created_at=now)
            messages._emitter.emit(uow, workspace_id=row['workspace_id'], stream=MESSAGE_STREAM, type=MESSAGE_CREATED_TYPE,
                payload=dict(message_id=message_id, channel_id=row['channel_id'], from_agent_id=row['agent_id'],
                    target=target, subject=message.subject, created_at=now, one_shot_call_id=row['call_id'],
                    system_notification=True), actor_agent_id=None, visibility='eligible', target=json.dumps(target))
            conn.execute('UPDATE one_shot_calls SET notification_message_id=? WHERE call_id=?', (message_id, row['call_id']))
        return len(rows)
