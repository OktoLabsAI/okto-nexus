-- Private host observations captured under an exact canonical close.
-- Verification supplies evidence of a retired source, never consent to open a successor.
CREATE TABLE embedded_codex_saved_contexts (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    owner_generation INTEGER NOT NULL CHECK (owner_generation >= 1),
    opening_operation_id TEXT NOT NULL,
    close_operation_id TEXT NOT NULL,
    stream_epoch TEXT NOT NULL,
    witness_json TEXT NOT NULL CHECK (json_valid(witness_json)),
    captured_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('CAPTURED', 'VERIFIED', 'FILE_CHANGED')),
    resolved_at TEXT,
    release_digest TEXT,
    PRIMARY KEY (server_id, executor_id, close_operation_id),
    CHECK ((status = 'CAPTURED' AND resolved_at IS NULL AND release_digest IS NULL)
        OR (status = 'FILE_CHANGED' AND resolved_at IS NOT NULL AND release_digest IS NULL)
        OR (status = 'VERIFIED' AND resolved_at IS NOT NULL AND release_digest IS NOT NULL)),
    FOREIGN KEY (server_id, executor_id, session_id)
        REFERENCES execution_sessions(server_id, executor_id, session_id),
    FOREIGN KEY (server_id, executor_id, close_operation_id)
        REFERENCES execution_operations(server_id, executor_id, operation_id)
);

CREATE INDEX embedded_codex_saved_contexts_pending
    ON embedded_codex_saved_contexts(server_id, executor_id)
    WHERE status = 'CAPTURED';

CREATE UNIQUE INDEX embedded_codex_saved_contexts_verified
    ON embedded_codex_saved_contexts(server_id, executor_id, session_id, owner_generation)
    WHERE status = 'VERIFIED';
