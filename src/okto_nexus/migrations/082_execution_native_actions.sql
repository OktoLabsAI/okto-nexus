-- Native action receipts and canonical handoff effects commit together.
CREATE TABLE execution_native_actions (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('context', 'claim', 'complete')),
    scope_json TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    claim_key TEXT,
    handoff_id TEXT NOT NULL REFERENCES handoffs(handoff_id),
    claim_epoch INTEGER NOT NULL CHECK (claim_epoch >= 0),
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (server_id, executor_id, session_id, action_id),
    UNIQUE (server_id, executor_id, session_id, claim_key),
    FOREIGN KEY (server_id, executor_id, session_id)
        REFERENCES execution_sessions(server_id, executor_id, session_id)
);
