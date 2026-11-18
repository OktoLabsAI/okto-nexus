-- Retain the human login and native target for a canonical session control.
CREATE TABLE session_interaction_controls (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    owner_generation INTEGER NOT NULL CHECK (typeof(owner_generation) = 'integer' AND owner_generation >= 1),
    authority_ref TEXT NOT NULL,
    surface TEXT NOT NULL CHECK (surface IN ('web', 'nexus_cli', 'native_terminal')),
    capability_revision TEXT NOT NULL,
    native_turn_id TEXT NOT NULL,
    PRIMARY KEY (server_id, executor_id, operation_id),
    FOREIGN KEY (server_id, executor_id, session_id)
        REFERENCES execution_sessions(server_id, executor_id, session_id),
    FOREIGN KEY (server_id, executor_id, operation_id)
        REFERENCES execution_operations(server_id, executor_id, operation_id)
);
