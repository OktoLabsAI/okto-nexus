-- A claim and its exact operations commit together. No productive dispatch
-- until the host confirms transfer of its original reservation to these IDs.
CREATE TABLE execution_capacity_admissions (
    domain_operation_id TEXT PRIMARY KEY REFERENCES delivery_outbox(operation_id),
    attempt_id TEXT NOT NULL UNIQUE,
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    reservation_json TEXT NOT NULL,
    consumption_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('WAITING_CONSUMPTION','CONSUMED','NEEDS_RECONCILIATION')),
    reason TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(server_id,executor_id,session_id) REFERENCES execution_sessions(server_id,executor_id,session_id)
);
CREATE INDEX execution_capacity_admissions_session ON execution_capacity_admissions(server_id,executor_id,session_id);
CREATE INDEX execution_capacity_admissions_pending ON execution_capacity_admissions(state,updated_at,domain_operation_id);
