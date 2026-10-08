"""Admit only new, unclaimed messages held while runtime ownership is recovered."""
import json
from types import SimpleNamespace
from ..domain.runtime_context import RuntimeRequestContext
from .runtime_policy import defaults


def drain_pending(deps):
    from ..adapters.inbound.mcp.tools.messages import build_service
    service=build_service(deps)
    with deps.connection_factory.unit_of_work() as uow:
        conn=uow.connection
        automatic_recovery = defaults(conn)['automatic_recovery']
        rows=conn.execute("SELECT p.*,d.message_id,d.recipient_agent_id,d.status delivery_status,d.consumer_kind,m.workspace_id "
            "FROM runtime_pending_deliveries p JOIN message_deliveries d USING(delivery_id) JOIN messages m USING(message_id) "
            "WHERE p.status='waiting' AND (? OR EXISTS(SELECT 1 FROM runtime_handoff_notifications n WHERE n.message_id=m.message_id)) "
            "ORDER BY p.attempts,p.created_at,p.delivery_id LIMIT 32", (automatic_recovery,)).fetchall()
        for row in rows:
            if row['delivery_status']!='unread' or row['consumer_kind'] is not None or conn.execute('SELECT 1 FROM delivery_outbox WHERE delivery_id=?',(row['delivery_id'],)).fetchone():
                conn.execute("UPDATE runtime_pending_deliveries SET status='resolved',reason='Already claimed or processed' WHERE delivery_id=?",(row['delivery_id'],))
                continue
            conn.execute('SAVEPOINT pending_message')
            try:
                message=deps.repos.messages.get(uow,workspace_id=row['workspace_id'],message_id=row['message_id'])
                context=RuntimeRequestContext(**json.loads(row['context_json']))
                if context.authentication_source == 'handoff_notification':
                    from .runtime_handoff_notifications import validate
                    validate(uow, message=message, recipient_id=row['recipient_agent_id'], agents=deps.repos.agents,
                             now=deps.clock.now_iso(), governance=service._governance)
                    service._runtime_planner.causality.record(uow, message=message, context=context, now=deps.clock.now_iso())
                op=service._runtime_planner.enqueue(uow,context=context,message=message,
                    delivery=SimpleNamespace(delivery_id=row['delivery_id'],recipient_agent_id=row['recipient_agent_id']),
                    now=deps.clock.now_iso(),authorization_revision=row['authorization_revision'],
                    result_source=json.loads(row['result_source_json']) if row['result_source_json'] else None)
                if op:
                    conn.execute("UPDATE runtime_pending_deliveries SET status='submitted' WHERE delivery_id=?",(row['delivery_id'],))
                else:
                    from .runtime_policy import effective
                    if not effective(conn, row['recipient_agent_id'])['runtime_enabled']:
                        conn.execute("UPDATE runtime_pending_deliveries SET status='resolved',reason='Runtime disabled; available through MCP' WHERE delivery_id=?", (row['delivery_id'],))
                    else:
                        conn.execute("UPDATE runtime_pending_deliveries SET attempts=attempts+1 "
                            "WHERE delivery_id=?", (row['delivery_id'],))
                conn.execute('RELEASE pending_message')
            except Exception as error:
                conn.execute('ROLLBACK TO pending_message')
                conn.execute('RELEASE pending_message')
                transient = getattr(error, 'code', None) == 'CONFLICT' and (
                    getattr(error, 'message', '') == 'Delivery session requires reconciliation.' or
                    bool(set(getattr(error, 'details', {}).get('blockers', ())) & {'inventory_not_fresh', 'executor_offline', 'executor_not_ready', 'agent_recovering'}))
                conn.execute("UPDATE runtime_pending_deliveries SET status=?,attempts=attempts+1,reason=? WHERE delivery_id=?",
                    ('waiting' if transient else 'attention', getattr(error,'code','RECOVERY_ADMISSION_FAILED'),row['delivery_id']))


def mark_recovery_attention(owner):
    """Initial retries exhausted; pending deliveries remain eligible for recovery."""
    owner.verify()
