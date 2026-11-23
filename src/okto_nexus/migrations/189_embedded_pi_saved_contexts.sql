-- Extend the private adapter constraint while preserving existing proofs and their order.
ALTER TABLE embedded_saved_contexts RENAME TO embedded_saved_contexts_previous;

CREATE TABLE embedded_saved_contexts (
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
    adapter_id TEXT NOT NULL DEFAULT 'codex_app_server'
        CHECK (adapter_id IN ('codex_app_server', 'claude_stream', 'pi_rpc')),
    PRIMARY KEY (server_id, executor_id, close_operation_id),
    CHECK ((status = 'CAPTURED' AND resolved_at IS NULL AND release_digest IS NULL)
        OR (status = 'FILE_CHANGED' AND resolved_at IS NOT NULL AND release_digest IS NULL)
        OR (status = 'VERIFIED' AND resolved_at IS NOT NULL AND release_digest IS NOT NULL)),
    FOREIGN KEY (server_id, executor_id, session_id)
        REFERENCES execution_sessions(server_id, executor_id, session_id),
    FOREIGN KEY (server_id, executor_id, close_operation_id)
        REFERENCES execution_operations(server_id, executor_id, operation_id)
);

INSERT INTO embedded_saved_contexts (
    rowid, server_id, executor_id, session_id, owner_generation, opening_operation_id,
    close_operation_id, stream_epoch, witness_json, captured_at, status, resolved_at,
    release_digest, adapter_id)
SELECT rowid, server_id, executor_id, session_id, owner_generation, opening_operation_id,
       close_operation_id, stream_epoch, witness_json, captured_at, status, resolved_at,
       release_digest, adapter_id
FROM embedded_saved_contexts_previous;

DROP TABLE embedded_saved_contexts_previous;

CREATE INDEX embedded_saved_contexts_pending
    ON embedded_saved_contexts(server_id, executor_id)
    WHERE status = 'CAPTURED';

CREATE UNIQUE INDEX embedded_saved_contexts_verified
    ON embedded_saved_contexts(server_id, executor_id, session_id, owner_generation)
    WHERE status = 'VERIFIED';
