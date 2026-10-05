ALTER TABLE execution_native_requests ADD COLUMN cas_token TEXT;
UPDATE execution_native_requests SET cas_token=lower(hex(randomblob(32)));
ALTER TABLE execution_decisions ADD COLUMN client_intent_id TEXT;
ALTER TABLE execution_decisions ADD COLUMN body_hash TEXT;
ALTER TABLE execution_decisions ADD COLUMN actor_guard_digest TEXT;
CREATE UNIQUE INDEX idx_execution_native_decision_once
    ON execution_decisions(server_id,executor_id,canonical_request_id)
    WHERE kind IN ('native_approval','native_input') AND native_operation_id IS NOT NULL;
CREATE UNIQUE INDEX idx_execution_decision_client_intent
    ON execution_decisions(server_id,actor_agent_id,client_intent_id)
    WHERE client_intent_id IS NOT NULL;
