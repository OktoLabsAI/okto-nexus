-- Host dispatch evidence is distinct from a receipt issued by Core.
CREATE TABLE execution_unsent_dispatch_proofs (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    attempt_no INTEGER NOT NULL CHECK(attempt_no >= 0),
    attempt_token TEXT,
    previous_owner TEXT,
    previous_generation INTEGER,
    fenced_by_owner TEXT,
    fenced_by_generation INTEGER,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY(server_id,executor_id,operation_id,attempt_no),
    FOREIGN KEY(server_id,executor_id,operation_id)
        REFERENCES execution_operations(server_id,executor_id,operation_id),
    CHECK(attempt_no=0 OR (attempt_token IS NOT NULL AND previous_owner IS NOT NULL
        AND previous_generation IS NOT NULL AND fenced_by_owner IS NOT NULL
        AND fenced_by_generation IS NOT NULL))
);
CREATE TABLE execution_unsent_delivery_history (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    domain_operation_id TEXT NOT NULL REFERENCES delivery_outbox(operation_id),
    attempt_number INTEGER NOT NULL CHECK(attempt_number > 0),
    endpoint_id TEXT NOT NULL REFERENCES agent_endpoints(endpoint_id),
    proof_operation_id TEXT NOT NULL,
    proof_attempt_no INTEGER NOT NULL,
    archived_at TEXT NOT NULL,
    PRIMARY KEY(server_id,executor_id,operation_id),
    FOREIGN KEY(server_id,executor_id,operation_id)
        REFERENCES execution_operations(server_id,executor_id,operation_id),
    FOREIGN KEY(server_id,executor_id,proof_operation_id,proof_attempt_no)
        REFERENCES execution_unsent_dispatch_proofs(server_id,executor_id,operation_id,attempt_no)
);
CREATE INDEX execution_unsent_delivery_source ON execution_unsent_delivery_history(domain_operation_id);
