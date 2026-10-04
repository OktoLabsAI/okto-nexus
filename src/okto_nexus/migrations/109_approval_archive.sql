-- Archiving dismisses the queue item without granting or delivering a decision.
-- Keep the original decision, payload and result for audit.
ALTER TABLE approvals ADD COLUMN archived_at TEXT;
ALTER TABLE approvals ADD COLUMN archived_by TEXT;
