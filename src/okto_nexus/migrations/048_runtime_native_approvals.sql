CREATE TABLE runtime_native_approvals (
    event_id TEXT PRIMARY KEY REFERENCES harness_events(event_id) ON DELETE RESTRICT,
    approval_id TEXT UNIQUE REFERENCES approvals(approval_id) ON DELETE RESTRICT,
    operation_id TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK(source_kind IN ('delivery_outbox','runtime_commands')),
    runtime_session_id TEXT NOT NULL REFERENCES harness_sessions(session_id) ON DELETE RESTRICT,
    connection_id TEXT NOT NULL,
    owner_epoch INTEGER NOT NULL,
    native_thread_id TEXT NOT NULL,
    native_turn_id TEXT NOT NULL,
    request_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    request_payload TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'NEW' CHECK(state IN ('NEW','PENDING','SENDING','SENT_UNCONFIRMED','NOT_SENT','OUTCOME_UNKNOWN')),
    decision TEXT,
    reason TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    UNIQUE(connection_id, request_key)
);
CREATE INDEX idx_runtime_native_approval_pending ON runtime_native_approvals(state,expires_at);
