CREATE TABLE execution_connection_resumes (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    connection_generation INTEGER NOT NULL,
    ticket_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (server_id, executor_id)
);
