-- Preserve immutable execution provenance when a proved-unsent delivery retries.
CREATE TABLE execution_delivery_attempt_history (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    domain_operation_id TEXT NOT NULL REFERENCES delivery_outbox(operation_id),
    attempt_number INTEGER NOT NULL CHECK(attempt_number > 0),
    endpoint_id TEXT NOT NULL REFERENCES agent_endpoints(endpoint_id),
    proof_operation_id TEXT NOT NULL,
    proof_receipt_revision INTEGER NOT NULL,
    archived_at TEXT NOT NULL,
    PRIMARY KEY(server_id, executor_id, operation_id),
    FOREIGN KEY(server_id, executor_id, operation_id)
        REFERENCES execution_operations(server_id, executor_id, operation_id),
    FOREIGN KEY(server_id, executor_id, proof_operation_id, proof_receipt_revision)
        REFERENCES execution_receipts(server_id, executor_id, operation_id, receipt_revision)
);
CREATE INDEX execution_delivery_attempt_source ON execution_delivery_attempt_history(domain_operation_id);

-- Earlier R4 deliveries did not use the legacy attempt counter. Their
-- immutable operation mapping proves that the first attempt was admitted.
UPDATE delivery_outbox SET attempt_count=1 WHERE attempt_count=0 AND EXISTS (
    SELECT 1 FROM execution_domain_deliveries m WHERE m.domain_operation_id=delivery_outbox.operation_id
);
