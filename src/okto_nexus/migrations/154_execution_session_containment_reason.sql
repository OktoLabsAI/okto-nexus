-- The reason a failed session was contained, so operators can see why it ended.
-- Written once, in the transaction that notifies the claimed handoff creators.
ALTER TABLE execution_sessions ADD COLUMN containment_reason TEXT;
ALTER TABLE execution_sessions ADD COLUMN contained_at TEXT;
