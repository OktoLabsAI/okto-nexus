-- foreign-key-rebuild
-- Preserve result IDs and every existing dependent foreign key.
CREATE TABLE runtime_results_rebuilt (
    result_id TEXT PRIMARY KEY,
    event_id TEXT UNIQUE REFERENCES harness_events(event_id) ON DELETE RESTRICT,
    runtime_session_id TEXT REFERENCES harness_sessions(session_id) ON DELETE RESTRICT,
    native_thread_id TEXT,
    native_turn_id TEXT,
    payload TEXT NOT NULL,
    publication_state TEXT NOT NULL DEFAULT 'PENDING_AUTHORIZATION',
    captured_at TEXT NOT NULL,
    operation_id TEXT REFERENCES delivery_outbox(operation_id) ON DELETE RESTRICT,
    attempt_id TEXT,
    output_text TEXT NOT NULL DEFAULT '',
    output_truncated INTEGER NOT NULL DEFAULT 0 CHECK(output_truncated IN (0,1)),
    output_event_count INTEGER NOT NULL DEFAULT 0,
    command_operation_id TEXT REFERENCES runtime_commands(operation_id) ON DELETE RESTRICT,
    publication_message_id TEXT REFERENCES messages(message_id) ON DELETE RESTRICT,
    publication_approval_id TEXT REFERENCES approvals(approval_id) ON DELETE RESTRICT,
    publication_response TEXT,
    publication_reason TEXT,
    output_artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
    artifact_reserved_bytes INTEGER NOT NULL DEFAULT 0 CHECK(artifact_reserved_bytes >= 0),
    artifact_generation INTEGER NOT NULL DEFAULT 0 CHECK(artifact_generation >= 0),
    delivery_outcome TEXT CHECK(delivery_outcome IN ('success','failed','interrupted')),
    relay_state TEXT NOT NULL DEFAULT 'NOT_REQUESTED',
    relay_reason TEXT,
    canonical_server_id TEXT,
    canonical_executor_id TEXT,
    canonical_operation_id TEXT,
    FOREIGN KEY(canonical_server_id,canonical_executor_id,canonical_operation_id)
        REFERENCES execution_results(server_id,executor_id,operation_id),
    CHECK((event_id IS NOT NULL AND runtime_session_id IS NOT NULL
        AND canonical_server_id IS NULL AND canonical_executor_id IS NULL AND canonical_operation_id IS NULL)
        OR (event_id IS NULL AND runtime_session_id IS NULL
        AND canonical_server_id IS NOT NULL AND canonical_executor_id IS NOT NULL AND canonical_operation_id IS NOT NULL))
);
INSERT INTO runtime_results_rebuilt(result_id,event_id,runtime_session_id,native_thread_id,native_turn_id,payload,publication_state,captured_at,operation_id,attempt_id,output_text,output_truncated,output_event_count,command_operation_id,publication_message_id,publication_approval_id,publication_response,publication_reason,output_artifact_id,artifact_reserved_bytes,artifact_generation,delivery_outcome,relay_state,relay_reason) SELECT result_id,event_id,runtime_session_id,native_thread_id,native_turn_id,payload,publication_state,captured_at,operation_id,attempt_id,output_text,output_truncated,output_event_count,command_operation_id,publication_message_id,publication_approval_id,publication_response,publication_reason,output_artifact_id,artifact_reserved_bytes,artifact_generation,delivery_outcome,relay_state,relay_reason FROM runtime_results;
DROP TABLE runtime_results;
ALTER TABLE runtime_results_rebuilt RENAME TO runtime_results;
CREATE INDEX runtime_results_session ON runtime_results(runtime_session_id, captured_at);
CREATE INDEX runtime_results_publication ON runtime_results(publication_state,captured_at) WHERE operation_id IS NOT NULL;
CREATE INDEX runtime_results_artifact_reservations ON runtime_results(result_id,operation_id,artifact_reserved_bytes) WHERE artifact_reserved_bytes > 0;
CREATE INDEX runtime_result_publication_message ON runtime_results(publication_message_id);
CREATE UNIQUE INDEX runtime_results_canonical_source ON runtime_results(canonical_server_id,canonical_executor_id,canonical_operation_id);
