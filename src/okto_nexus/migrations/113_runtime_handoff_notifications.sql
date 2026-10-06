CREATE TABLE runtime_handoff_notifications (
 message_id TEXT PRIMARY KEY REFERENCES messages(message_id),
 handoff_id TEXT NOT NULL REFERENCES handoffs(handoff_id),
 recipient_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
 event_type TEXT NOT NULL,
 actor_guard TEXT NOT NULL,
 UNIQUE(handoff_id, recipient_agent_id, event_type)
);
