-- Retain the exact capacity request before crossing the host boundary.
CREATE TABLE session_interaction_capacity_attempts (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    input_id TEXT NOT NULL,
    input_revision INTEGER NOT NULL CHECK (typeof(input_revision) = 'integer' AND input_revision >= 0),
    request_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PREPARED', 'STAGED')),
    operation_id TEXT,
    reservation_json TEXT,
    consumption_json TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    PRIMARY KEY (server_id, executor_id, attempt_id),
    UNIQUE (server_id, executor_id, operation_id),
    FOREIGN KEY (server_id, executor_id, session_id, input_id)
        REFERENCES session_interaction_inputs(server_id, executor_id, session_id, input_id),
    FOREIGN KEY (server_id, executor_id, operation_id)
        REFERENCES execution_operations(server_id, executor_id, operation_id),
    CHECK (attempt_id = input_id || ':' || input_revision),
    CHECK ((state = 'PREPARED' AND operation_id IS NULL AND reservation_json IS NULL AND consumption_json IS NULL)
        OR (state = 'STAGED' AND operation_id IS NOT NULL AND reservation_json IS NOT NULL AND consumption_json IS NOT NULL))
);

CREATE UNIQUE INDEX idx_session_capacity_attempt_unresolved
    ON session_interaction_capacity_attempts(server_id, executor_id, session_id)
    WHERE state = 'PREPARED' AND resolved_at IS NULL;
