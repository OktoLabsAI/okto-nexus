ALTER TABLE runtime_results ADD COLUMN publication_message_id TEXT REFERENCES messages(message_id) ON DELETE RESTRICT;
ALTER TABLE runtime_results ADD COLUMN publication_approval_id TEXT REFERENCES approvals(approval_id) ON DELETE RESTRICT;
ALTER TABLE runtime_results ADD COLUMN publication_response TEXT;
ALTER TABLE runtime_results ADD COLUMN publication_reason TEXT;
CREATE INDEX runtime_results_publication ON runtime_results(publication_state,captured_at) WHERE operation_id IS NOT NULL;
-- Upgrading is not authority to send historical results to other agents.
UPDATE runtime_results SET publication_state='REVIEW_REQUIRED',publication_reason='predates_publication_contract' WHERE publication_state='PENDING_AUTHORIZATION' AND operation_id IS NOT NULL;
