-- Logical STARTING is the existing durable open request, before native I/O.
ALTER TABLE runtime_open_requests ADD COLUMN endpoint_id TEXT REFERENCES agent_endpoints(endpoint_id) ON DELETE RESTRICT;
ALTER TABLE runtime_open_requests ADD COLUMN endpoint_revision INTEGER;
ALTER TABLE runtime_open_requests ADD COLUMN profile_revision INTEGER;
ALTER TABLE runtime_open_requests ADD COLUMN owner_epoch INTEGER;
ALTER TABLE runtime_open_requests ADD COLUMN owner_id TEXT;
ALTER TABLE runtime_open_requests ADD COLUMN deadline TEXT;
CREATE INDEX idx_runtime_start_recovery ON runtime_open_requests(status,owner_epoch,endpoint_id);
CREATE INDEX idx_runtime_session_recovery ON harness_sessions(owner_epoch,lifecycle_state);
