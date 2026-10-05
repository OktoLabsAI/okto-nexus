-- Nonexecuting transport attempts subordinate to one canonical inbox intent.
-- They never own a delivery, claim, execution budget or runtime result.
CREATE TABLE runtime_context_observations (
    operation_id TEXT PRIMARY KEY,
    source_operation_id TEXT NOT NULL REFERENCES delivery_outbox(operation_id) ON DELETE RESTRICT,
    endpoint_id TEXT NOT NULL REFERENCES agent_endpoints(endpoint_id) ON DELETE RESTRICT,
    endpoint_revision INTEGER NOT NULL,
    profile_revision INTEGER,
    runtime_session_id TEXT NOT NULL REFERENCES harness_sessions(session_id) ON DELETE RESTRICT,
    expected_owner_epoch INTEGER NOT NULL,
    envelope TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','CLAIMED','SENDING','SENT_UNCONFIRMED','OUTCOME_UNKNOWN','REJECTED','CANCELLED')),
    owner_epoch INTEGER,
    attempt_id TEXT,
    reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_operation_id,endpoint_id)
);
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
