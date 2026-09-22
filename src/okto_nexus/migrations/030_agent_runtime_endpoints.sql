-- Additive PR34 remediation. No legacy Agent/profile data is rewritten.
CREATE TABLE runtime_profiles (
    profile_id TEXT PRIMARY KEY,
    adapter_id TEXT NOT NULL,
    config TEXT NOT NULL,
    secret_refs TEXT NOT NULL DEFAULT '{}',
    inherit_ambient INTEGER NOT NULL DEFAULT 0 CHECK (inherit_ambient IN (0,1)),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0,1)),
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE agent_endpoints (
    endpoint_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
    adapter_id TEXT NOT NULL,
    protocol TEXT NOT NULL,
    contract_version INTEGER NOT NULL DEFAULT 1,
    profile_id TEXT REFERENCES runtime_profiles(profile_id) ON DELETE RESTRICT,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0,1)),
    activation_state TEXT NOT NULL DEFAULT 'pending_review',
    priority INTEGER NOT NULL DEFAULT 0,
    selection_group TEXT,
    consumption TEXT NOT NULL DEFAULT 'exclusive',
    response_policy TEXT NOT NULL DEFAULT 'explicit',
    public_config TEXT NOT NULL DEFAULT '{}',
    health TEXT NOT NULL DEFAULT 'unknown',
    health_reason TEXT,
    last_observed_at TEXT,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_endpoint_selection ON agent_endpoints(agent_id,workspace_id,enabled,priority);
ALTER TABLE harness_sessions ADD COLUMN endpoint_id TEXT REFERENCES agent_endpoints(endpoint_id) ON DELETE RESTRICT;
ALTER TABLE harness_sessions ADD COLUMN workspace_id TEXT REFERENCES workspaces(workspace_id) ON DELETE RESTRICT;
ALTER TABLE harness_sessions ADD COLUMN presence_session_id TEXT REFERENCES sessions(session_id) ON DELETE RESTRICT;
ALTER TABLE harness_sessions ADD COLUMN owner_epoch INTEGER;
ALTER TABLE harness_sessions ADD COLUMN connection_id TEXT;
ALTER TABLE harness_sessions ADD COLUMN lifecycle_state TEXT NOT NULL DEFAULT 'legacy_unlinked';
CREATE INDEX idx_harness_endpoint ON harness_sessions(endpoint_id,workspace_id,lifecycle_state);
-- One physical line is intentional: the existing SQL runner is line framed.
CREATE TRIGGER retain_harness_agent_history BEFORE DELETE ON agents WHEN EXISTS (SELECT 1 FROM harness_sessions WHERE owning_agent_id=OLD.agent_id) BEGIN SELECT RAISE(ABORT,'Deactivate agent instead of deleting runtime audit history'); END;
