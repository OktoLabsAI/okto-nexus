-- Captured requests have no deciding actor. Decisions remain in execution_decisions.
CREATE TABLE execution_native_requests (
    canonical_request_id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    stream_epoch TEXT NOT NULL,
    session_owner_generation INTEGER NOT NULL CHECK (session_owner_generation >= 1),
    source_operation_id TEXT NOT NULL,
    source_sequence INTEGER NOT NULL CHECK (source_sequence >= 1),
    native_request_id_json TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('native_approval','native_input')),
    request_revision INTEGER NOT NULL CHECK (request_revision >= 1),
    request_hash TEXT NOT NULL,
    operational_frame_json TEXT NOT NULL,
    display_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PENDING','STALE','EXPIRED','DECIDED')),
    received_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    UNIQUE (server_id,executor_id,session_id,stream_epoch,session_owner_generation,native_request_id_json),
    FOREIGN KEY (server_id,executor_id,source_operation_id)
        REFERENCES execution_operations(server_id,executor_id,operation_id),
    FOREIGN KEY (server_id,executor_id,session_id,stream_epoch,source_sequence)
        REFERENCES execution_event_ingress(server_id,executor_id,session_id,stream_epoch,sequence)
);
CREATE INDEX idx_execution_native_requests_pending
    ON execution_native_requests(server_id,executor_id,session_id,state,expires_at);
