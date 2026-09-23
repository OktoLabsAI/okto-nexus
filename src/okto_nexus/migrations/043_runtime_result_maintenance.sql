ALTER TABLE runtime_results ADD COLUMN artifact_generation INTEGER NOT NULL DEFAULT 0 CHECK(artifact_generation >= 0);
CREATE TABLE runtime_artifact_settings (singleton INTEGER PRIMARY KEY CHECK(singleton=1),quota_bytes INTEGER NOT NULL CHECK(quota_bytes BETWEEN 262144 AND 1073741824));
INSERT INTO runtime_artifact_settings VALUES(1,67108864);
CREATE TABLE runtime_result_maintenance (
    maintenance_id TEXT PRIMARY KEY,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('cleanup','retry','quota')),
    result_id TEXT REFERENCES runtime_results(result_id) ON DELETE RESTRICT,
    artifact_id TEXT,
    artifact_generation INTEGER,
    workspace_id TEXT,
    agent_id TEXT,
    reserved_bytes INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','DONE')),
    response TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(actor_agent_id,idempotency_key)
);
CREATE UNIQUE INDEX runtime_result_pending_cleanup ON runtime_result_maintenance(result_id) WHERE action='cleanup' AND status='PENDING';
