-- Keep the complete reviewed proposal and its exact request digest.
ALTER TABLE execution_proposals ADD COLUMN body_hash TEXT;
ALTER TABLE execution_proposals ADD COLUMN proposal_revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE execution_proposals ADD COLUMN proposal_json TEXT;
ALTER TABLE execution_proposals ADD COLUMN applied_json TEXT;
