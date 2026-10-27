-- Per-endpoint choice of how the hub treats a newer build of an approved runtime (#89).
-- NULL inherits the hub setting. The column is outside the configuration digest and
-- the session guard, so an edit never revokes grants or closes live sessions.
ALTER TABLE agent_endpoints ADD COLUMN runtime_update_policy TEXT
    CHECK (runtime_update_policy IS NULL OR runtime_update_policy IN ('review','follow'));

-- Append-only audit of every decision about a successor build of an installation.
-- The integer id orders the rows and is the id of the operator accept route.
-- 'in_place' marks an update that keeps the approved ref: every policy accepts it.
CREATE TABLE execution_installation_succession (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    stable_ref TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('accepted','held')),
    reason TEXT NOT NULL,
    policy TEXT NOT NULL CHECK (policy IN ('review','follow','in_place')),
    policy_source TEXT NOT NULL CHECK (policy_source IN ('hub','endpoint')),
    decided_by TEXT NOT NULL,
    from_executable TEXT,
    to_executable TEXT,
    from_version TEXT,
    to_version TEXT,
    from_build_identity TEXT,
    to_build_identity TEXT NOT NULL,
    from_fingerprint TEXT,
    to_fingerprint TEXT,
    to_natural_ref TEXT,
    decided_at TEXT NOT NULL,
    UNIQUE (server_id, executor_id, stable_ref, to_build_identity, decision)
);

CREATE TRIGGER execution_installation_succession_no_update
BEFORE UPDATE ON execution_installation_succession
BEGIN SELECT RAISE(ABORT, 'execution_installation_succession_append_only'); END;

CREATE TRIGGER execution_installation_succession_no_delete
BEFORE DELETE ON execution_installation_succession
BEGIN SELECT RAISE(ABORT, 'execution_installation_succession_append_only'); END;
