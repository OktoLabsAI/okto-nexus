-- Preserve the existing transport decision taxonomy; record the separate
-- canonical claim transition alongside it, in the same audit and transaction.
ALTER TABLE runtime_operation_reconciliations ADD COLUMN canonical_action TEXT
    CHECK(canonical_action IS NULL OR canonical_action='reopen_handoff');
ALTER TABLE runtime_operation_reconciliations ADD COLUMN handoff_id TEXT
    REFERENCES handoffs(handoff_id) ON DELETE RESTRICT;
ALTER TABLE runtime_operation_reconciliations ADD COLUMN claim_epoch INTEGER;
CREATE INDEX idx_runtime_reconciliation_handoff ON runtime_operation_reconciliations(handoff_id,claim_epoch);
