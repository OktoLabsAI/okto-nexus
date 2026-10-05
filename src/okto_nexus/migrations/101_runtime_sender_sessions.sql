-- Default preserves shared sessions. Sender affinity is server-owned and durable.
ALTER TABLE agent_endpoints ADD COLUMN session_policy TEXT NOT NULL DEFAULT 'shared'
    CHECK (session_policy IN ('shared', 'per_sender'));

CREATE TABLE execution_sender_sessions (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    sender_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    PRIMARY KEY (server_id, executor_id, session_id),
    FOREIGN KEY (server_id, executor_id, session_id)
        REFERENCES execution_sessions(server_id, executor_id, session_id)
);
CREATE INDEX execution_sender_sessions_sender
    ON execution_sender_sessions(sender_agent_id, server_id, executor_id);
