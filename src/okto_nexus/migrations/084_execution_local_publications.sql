-- Core/R4 semantic binding committed before the embedded native effect.
CREATE TABLE execution_local_publications (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    binding_json TEXT NOT NULL,
    terminal INTEGER NOT NULL DEFAULT 0 CHECK (terminal IN (0,1)),
    PRIMARY KEY(server_id,executor_id,operation_id),
    FOREIGN KEY(server_id,executor_id,operation_id)
        REFERENCES execution_operations(server_id,executor_id,operation_id)
);
