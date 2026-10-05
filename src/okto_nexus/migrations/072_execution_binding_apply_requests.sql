-- Recover a committed apply without interpreting a second POST as creation.
ALTER TABLE execution_proposals ADD COLUMN apply_client_intent_id TEXT;
ALTER TABLE execution_proposals ADD COLUMN apply_body_hash TEXT;
CREATE UNIQUE INDEX idx_execution_proposal_apply_intent ON execution_proposals(server_id,actor_agent_id,apply_client_intent_id);
