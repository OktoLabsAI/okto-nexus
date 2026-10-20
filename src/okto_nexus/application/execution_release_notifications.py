"""Server status replies for proven session release without a final result.

The original admitted conversation supplies every identity. These notices are
not native output, acknowledgements, successful handoff completion or automatic
runtime relays. One-shot calls already own a separate error-notification path.
"""
import hashlib
import json

from ..domain.messages import MESSAGE_CREATED_TYPE, MESSAGE_STREAM


def publish_release_notifications(deps, messages):
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        rows = conn.execute(
            "SELECT r.domain_operation_id,r.operation_id,r.session_id,d.workspace_id,"
            "d.message_id,d.recipient_agent_id,m.from_agent_id AS caller_id,m.channel_id "
            "FROM execution_release_notifications n INDEXED BY execution_release_notifications_pending "
            "CROSS JOIN execution_delivery_releases r ON r.domain_operation_id=n.domain_operation_id "
            "CROSS JOIN execution_sessions s USING(server_id,executor_id,session_id) "
            "CROSS JOIN execution_operations o USING(server_id,executor_id,operation_id) "
            "CROSS JOIN execution_domain_deliveries x USING(server_id,executor_id,operation_id) "
            "CROSS JOIN delivery_outbox d ON d.operation_id=r.domain_operation_id "
            "CROSS JOIN messages m ON m.message_id=d.message_id "
            "WHERE n.state='PENDING' AND x.domain_operation_id=r.domain_operation_id AND o.session_id=r.session_id "
            "AND o.action='turn.submit' AND o.subject_agent_id=d.recipient_agent_id "
            "AND s.lifecycle_state='CLOSED' AND s.lease_state='CLOSED' "
            "AND d.workspace_id=m.workspace_id AND d.actor_agent_id=m.from_agent_id "
            "AND d.reconciliation_id IS NULL AND d.canonical_terminal_operation_id IS NULL "
            "AND d.terminal_event_id IS NULL AND d.external_completed_at IS NULL "
            "AND d.status='OUTCOME_UNKNOWN' AND d.reason='session_released_without_result' "
            "AND NOT EXISTS (SELECT 1 FROM one_shot_calls c WHERE c.call_id=r.domain_operation_id) "
            "AND NOT EXISTS (SELECT 1 FROM runtime_handoff_notice_retirements n "
            "WHERE n.operation_id=r.domain_operation_id) "
            "AND NOT EXISTS (SELECT 1 FROM execution_capacity_compensations c "
            "WHERE c.domain_operation_id=r.domain_operation_id) "
            "ORDER BY n.created_at,n.domain_operation_id LIMIT 32").fetchall()
        for row in rows:
            identity = hashlib.sha256(row['domain_operation_id'].encode()).hexdigest()
            message_id = 'msg_runtime_release_' + identity
            target = dict(strategy='direct', agent_id=row['caller_id'])
            now = deps.clock.now_iso()
            subject = 'Nexus runtime interrupted'
            body = (
                'RUNTIME_SESSION_ENDED: The runtime session ended before a final response was recorded. '
                'The session has been closed and this request will not be replayed automatically. '
                'Actions may already have taken effect; check their outcome before retrying.\n\n'
                f"Request: {row['domain_operation_id']}\nSession: {row['session_id']}")
            messages._messages.create(uow, message_id=message_id, workspace_id=row['workspace_id'],
                from_agent_id=row['recipient_agent_id'], channel_id=row['channel_id'], from_session_id=None,
                target=json.dumps(target), subject=subject, body=body, artifacts=[],
                parent_message_id=row['message_id'], trace_id=None, created_at=now)
            messages._deliveries.create(uow, delivery_id='del_runtime_release_' + identity,
                message_id=message_id, recipient_agent_id=row['caller_id'], status='unread', created_at=now)
            messages._emitter.emit(uow, workspace_id=row['workspace_id'], stream=MESSAGE_STREAM,
                type=MESSAGE_CREATED_TYPE, payload=dict(message_id=message_id, channel_id=row['channel_id'],
                    from_agent_id=row['recipient_agent_id'], target=target, subject=subject, created_at=now,
                    runtime_operation_id=row['domain_operation_id'], system_notification=True),
                actor_agent_id=None, visibility='eligible', target=json.dumps(target))
            conn.execute("UPDATE execution_release_notifications SET message_id=?,state='PUBLISHED' "
                "WHERE domain_operation_id=? AND state='PENDING'", (message_id, row['domain_operation_id']))
        return len(rows)
