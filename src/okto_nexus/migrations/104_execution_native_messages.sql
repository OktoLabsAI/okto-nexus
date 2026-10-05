-- Native message receipt and canonical message/approval commit together.
CREATE TABLE execution_native_messages (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action = 'message_create'),
    scope_json TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (server_id, executor_id, session_id, action_id),
    FOREIGN KEY (server_id, executor_id, session_id)
        REFERENCES execution_sessions(server_id, executor_id, session_id)
);
