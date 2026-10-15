-- Scheduling leases bound duplicate scans; they are NOT handoff ownership.
CREATE TABLE handoff_runtime_schedule (
    handoff_id TEXT NOT NULL REFERENCES handoffs(handoff_id),
    claim_generation INTEGER NOT NULL CHECK(claim_generation >= 0),
    workspace_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('PENDING','IDLE')),
    due_at REAL NOT NULL,
    reason TEXT,
    backoff_count INTEGER NOT NULL DEFAULT 0,
    candidate_cursor TEXT NOT NULL DEFAULT '',
    wake_revision INTEGER NOT NULL DEFAULT 0,
    seen_wake_generation INTEGER NOT NULL DEFAULT 0,
    lease_token TEXT,
    lease_until REAL NOT NULL DEFAULT 0,
    PRIMARY KEY(handoff_id,claim_generation)
);
CREATE INDEX handoff_runtime_schedule_due ON handoff_runtime_schedule(state,due_at,lease_until);
CREATE TABLE handoff_runtime_schedule_scan (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    wake_generation INTEGER NOT NULL DEFAULT 0,
    handoff_cursor INTEGER NOT NULL DEFAULT 0,
    attempt_cursor INTEGER NOT NULL DEFAULT 0
);
INSERT INTO handoff_runtime_schedule_scan(singleton) VALUES(1);
-- Historical completions and directed work must not stretch recovery latency.
CREATE INDEX handoff_runtime_open_broadcast ON handoffs(status)
    WHERE status='OPEN' AND CASE WHEN json_valid(target) THEN json_extract(target,'$.strategy') END='broadcast';
CREATE INDEX handoff_runtime_active_attempts ON handoff_runtime_attempts(active) WHERE active=1;
