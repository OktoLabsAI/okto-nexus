-- A removed runtime identity remains as a tombstone so historical foreign keys
-- continue to identify the original actor without granting it access.
ALTER TABLE agents ADD COLUMN deleted_at TEXT;
CREATE INDEX idx_agents_visible ON agents(deleted_at, created_at, agent_id);
