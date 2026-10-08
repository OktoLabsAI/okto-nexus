-- Keep historical observation identities without forging legacy sessions.
ALTER TABLE runtime_context_observations RENAME TO old_runtime_context_observations;
DROP INDEX idx_context_observation_pending;
DROP INDEX idx_context_observation_endpoint;
DROP TRIGGER runtime_context_capture_admission;
DROP TRIGGER runtime_context_observation_capacity;
CREATE TABLE runtime_context_observations (
    operation_id TEXT PRIMARY KEY,
    source_operation_id TEXT NOT NULL REFERENCES delivery_outbox(operation_id) ON DELETE RESTRICT,
    endpoint_id TEXT NOT NULL REFERENCES agent_endpoints(endpoint_id) ON DELETE RESTRICT,
    endpoint_revision INTEGER NOT NULL,
    profile_revision INTEGER,
    runtime_session_id TEXT NOT NULL,
    expected_owner_epoch INTEGER NOT NULL,
    envelope TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','CLAIMED','SENDING','SENT_UNCONFIRMED','OUTCOME_UNKNOWN','REJECTED','CANCELLED')),
    owner_epoch INTEGER,
    attempt_id TEXT,
    reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    legacy_session_id TEXT REFERENCES harness_sessions(session_id) ON DELETE RESTRICT,
    canonical_server_id TEXT,
    canonical_executor_id TEXT,
    FOREIGN KEY(canonical_server_id,canonical_executor_id,runtime_session_id)
        REFERENCES execution_sessions(server_id,executor_id,session_id) ON DELETE RESTRICT,
    CHECK ((legacy_session_id IS NOT NULL AND legacy_session_id=runtime_session_id AND canonical_server_id IS NULL AND canonical_executor_id IS NULL)
        OR (legacy_session_id IS NULL AND canonical_server_id IS NOT NULL AND canonical_executor_id IS NOT NULL)),
    UNIQUE(source_operation_id,endpoint_id)
);
INSERT INTO runtime_context_observations SELECT *,runtime_session_id,NULL,NULL FROM old_runtime_context_observations;
DROP TABLE old_runtime_context_observations;
CREATE INDEX idx_context_observation_pending ON runtime_context_observations(status,created_at,operation_id);
CREATE INDEX idx_context_observation_endpoint ON runtime_context_observations(endpoint_id,status);
CREATE TRIGGER runtime_context_capture_admission
BEFORE INSERT ON runtime_context_observations
WHEN (SELECT capture_available FROM runtime_writer_contract WHERE singleton=1)=0
BEGIN
    SELECT RAISE(ABORT, 'runtime_capture_unavailable');
END;
CREATE TRIGGER runtime_context_observation_capacity
BEFORE INSERT ON runtime_context_observations
WHEN (SELECT count(*) FROM runtime_context_observations WHERE status IN ('PENDING','CLAIMED','SENDING','OUTCOME_UNKNOWN')) >= 256
 OR (SELECT COALESCE(sum(length(CAST(envelope AS BLOB))),0) FROM runtime_context_observations WHERE status IN ('PENDING','CLAIMED','SENDING','OUTCOME_UNKNOWN')) + length(CAST(NEW.envelope AS BLOB)) > 4194304
BEGIN
    SELECT RAISE(ABORT, 'runtime_context_backpressure');
END;
-- Only the owning embedded Core may publish observed context-only support.
CREATE TABLE execution_context_observers (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    owner_instance_id TEXT NOT NULL,
    executor_generation INTEGER NOT NULL,
    owner_epoch INTEGER NOT NULL,
    profile_revision INTEGER NOT NULL,
    qualified INTEGER NOT NULL CHECK(qualified IN (0,1)),
    PRIMARY KEY(server_id,executor_id,session_id),
    FOREIGN KEY(server_id,executor_id,session_id)
        REFERENCES execution_sessions(server_id,executor_id,session_id) ON DELETE RESTRICT
);
