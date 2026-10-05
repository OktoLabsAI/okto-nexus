-- Canonical output keeps R4 provenance, never synthetic legacy harness rows.
CREATE TABLE execution_results (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    stream_epoch TEXT NOT NULL,
    terminal_sequence INTEGER,
    output_text TEXT NOT NULL DEFAULT '',
    output_truncated INTEGER NOT NULL DEFAULT 0 CHECK(output_truncated IN (0,1)),
    output_event_count INTEGER NOT NULL DEFAULT 0 CHECK(output_event_count >= 0),
    delivery_outcome TEXT,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(server_id,executor_id,operation_id),
    FOREIGN KEY(server_id,executor_id,operation_id)
        REFERENCES execution_operations(server_id,executor_id,operation_id),
    FOREIGN KEY(server_id,executor_id,session_id,stream_epoch,terminal_sequence)
        REFERENCES execution_event_ingress(server_id,executor_id,session_id,stream_epoch,sequence)
);
