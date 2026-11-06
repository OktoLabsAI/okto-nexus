-- Fence delayed compensation and execution against a later operator decision.
-- Timestamps are not generations: injected clocks and concurrent retries may
-- have identical decided_at values. Original payload/result stay unchanged.
ALTER TABLE approvals ADD COLUMN decision_revision INTEGER NOT NULL DEFAULT 0;
