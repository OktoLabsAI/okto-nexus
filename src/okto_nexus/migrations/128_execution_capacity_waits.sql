-- Flow control only: neither an execution receipt nor canonical work ownership.
CREATE TABLE execution_capacity_waits (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    connection_generation INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('WAITING','RUNNING')),
    frame_json TEXT NOT NULL,
    PRIMARY KEY(server_id,executor_id,operation_id),
    FOREIGN KEY(server_id,executor_id,operation_id)
        REFERENCES execution_operations(server_id,executor_id,operation_id) ON DELETE CASCADE
);
