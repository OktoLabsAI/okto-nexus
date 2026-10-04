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
        if not defaults(conn)['automatic_recovery']: return
        rows=conn.execute("SELECT p.*,d.message_id,d.recipient_agent_id,d.status delivery_status,d.consumer_kind,m.workspace_id "
            "FROM runtime_pending_deliveries p JOIN message_deliveries d USING(delivery_id) JOIN messages m USING(message_id) "
            "WHERE p.status='waiting' ORDER BY p.attempts,p.created_at,p.delivery_id LIMIT 32").fetchall()
        for row in rows:
            if row['delivery_status']!='unread' or row['consumer_kind'] is not None or conn.execute('SELECT 1 FROM delivery_outbox WHERE delivery_id=?',(row['delivery_id'],)).fetchone():
                conn.execute("UPDATE runtime_pending_deliveries SET status='resolved',reason='Already claimed or processed' WHERE delivery_id=?",(row['delivery_id'],))
                continue
            conn.execute('SAVEPOINT pending_message')
            try:
                message=deps.repos.messages.get(uow,workspace_id=row['workspace_id'],message_id=row['message_id'])
                context=RuntimeRequestContext(**json.loads(row['context_json']))
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
                        conn.execute("UPDATE runtime_pending_deliveries SET attempts=attempts+1,"
                            "status=CASE WHEN attempts>=119 THEN 'attention' ELSE status END,"
                            "reason=CASE WHEN attempts>=119 THEN 'Recovery wait limit reached; message was not submitted' ELSE reason END "
                            "WHERE delivery_id=?", (row['delivery_id'],))
                conn.execute('RELEASE pending_message')
            except Exception as error:
                conn.execute('ROLLBACK TO pending_message')
                conn.execute('RELEASE pending_message')
                conn.execute("UPDATE runtime_pending_deliveries SET status='attention',reason=? WHERE delivery_id=?",
                    (getattr(error,'code','RECOVERY_ADMISSION_FAILED'),row['delivery_id']))


def mark_recovery_attention(owner):
    """Stop queue retries for the exhausted executor without claiming messages."""
    with owner.factory.unit_of_work() as uow:
        owner.verify(uow=uow)
        uow.connection.execute("UPDATE runtime_pending_deliveries SET status='attention',"
            "reason='Automatic runtime recovery attempts exhausted' WHERE status='waiting' AND delivery_id IN ("
            "SELECT d.delivery_id FROM message_deliveries d JOIN agent_endpoints ep ON ep.agent_id=d.recipient_agent_id "
            "JOIN execution_bindings b ON b.endpoint_id=ep.endpoint_id WHERE b.executor_id=?)", (owner.channel.executor_id,))
