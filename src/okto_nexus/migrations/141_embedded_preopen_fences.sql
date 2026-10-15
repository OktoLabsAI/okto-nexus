-- Retain the exact Core admission fence before touching an interrupted opening.
CREATE TABLE execution_local_preopen_fences (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    refusal_json TEXT NOT NULL CHECK(json_valid(refusal_json)),
    PRIMARY KEY(server_id, executor_id, operation_id),
    FOREIGN KEY(server_id, executor_id, operation_id)
        REFERENCES execution_operations(server_id, executor_id, operation_id)
);
