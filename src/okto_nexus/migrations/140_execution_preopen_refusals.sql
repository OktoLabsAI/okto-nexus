-- Positive Core admission fences, accepted only by the replacement control
-- owner. Preserve both the original association and the physical release fact.
CREATE TABLE execution_preopen_refusals (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    report_json TEXT NOT NULL,
    report_digest TEXT NOT NULL,
    accepted_connection_id TEXT NOT NULL,
    accepted_generation INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY(server_id,executor_id,operation_id),
    FOREIGN KEY(server_id,executor_id,operation_id)
        REFERENCES execution_operations(server_id,executor_id,operation_id)
);
