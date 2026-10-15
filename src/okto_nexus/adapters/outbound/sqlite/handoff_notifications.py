"""Persist server-authored notice routing without changing MCP delivery state."""


class SqliteHandoffNotificationRepository:
    def record(self, uow, *, message_id, handoff_id, recipient_id, event_type, actor_guard, competitive):
        uow.connection.execute('INSERT INTO runtime_handoff_notifications '
            '(message_id,handoff_id,recipient_agent_id,event_type,actor_guard,runtime_route) VALUES(?,?,?,?,?,?)',
            (message_id, handoff_id, recipient_id, event_type, actor_guard,
             'competitive' if competitive else 'conversation'))

    def competitive(self, uow, *, message_id, recipient_id):
        return uow.connection.execute("SELECT 1 FROM runtime_handoff_notifications "
            "WHERE message_id=? AND recipient_agent_id=? AND runtime_route='competitive'",
            (message_id, recipient_id)).fetchone() is not None
