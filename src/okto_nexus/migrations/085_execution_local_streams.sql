CREATE TABLE execution_local_streams (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    stream_epoch TEXT NOT NULL,
    opening_operation_id TEXT NOT NULL,
    binding_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    PRIMARY KEY (server_id, executor_id, session_id, stream_epoch),
    FOREIGN KEY (server_id, executor_id, opening_operation_id)
        REFERENCES execution_operations(server_id, executor_id, operation_id)
);
