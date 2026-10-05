-- A canonical handoff claim may be owned by one managed session generation.
CREATE TABLE execution_tool_claims (
    handoff_id TEXT NOT NULL REFERENCES handoffs(handoff_id),
    claim_epoch INTEGER NOT NULL CHECK (claim_epoch >= 1),
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    PRIMARY KEY (handoff_id, claim_epoch),
    FOREIGN KEY (server_id, executor_id, session_id)
        REFERENCES execution_sessions(server_id, executor_id, session_id)
);
