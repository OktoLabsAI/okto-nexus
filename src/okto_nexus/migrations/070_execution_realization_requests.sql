-- An opaque realization publication is recoverable by its original intent.
ALTER TABLE execution_realizations ADD COLUMN client_intent_id TEXT;
ALTER TABLE execution_realizations ADD COLUMN body_hash TEXT;
ALTER TABLE execution_realizations ADD COLUMN local_consent_id TEXT;
CREATE UNIQUE INDEX idx_execution_realization_intent ON execution_realizations(server_id,executor_id,subject_agent_id,client_intent_id);
