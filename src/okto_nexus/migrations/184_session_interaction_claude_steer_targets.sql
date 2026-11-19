CREATE TABLE session_interaction_claude_steer_targets (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    target_operation_id TEXT NOT NULL CHECK (target_operation_id <> operation_id),
    target_stream_epoch TEXT NOT NULL CHECK (length(target_stream_epoch) BETWEEN 1 AND 160),
    PRIMARY KEY (server_id, executor_id, operation_id),
    FOREIGN KEY (server_id, executor_id, operation_id)
        REFERENCES session_interaction_controls(server_id, executor_id, operation_id),
    FOREIGN KEY (server_id, executor_id, target_operation_id)
        REFERENCES execution_operations(server_id, executor_id, operation_id)
);
