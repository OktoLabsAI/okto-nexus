-- Exact admission charge belongs to the durable operation ID.
ALTER TABLE execution_operations ADD COLUMN admission_bytes INTEGER NOT NULL DEFAULT 0
    CHECK (admission_bytes >= 0);
-- Retained native input uses a reference instead of plaintext. Conservatively
-- charge the maximum response size for historical rows whose exact cost is lost.
UPDATE execution_operations SET admission_bytes =
    length(CAST(semantic_payload AS BLOB)) +
    CASE WHEN action = 'input.provide' THEN 16384 ELSE 0 END;
CREATE INDEX idx_execution_pending_admission
ON execution_operations(server_id, executor_id, action, admission_bytes)
WHERE admission_state IN ('ACCEPTED','DISPATCH_PENDING','RECONCILING');
