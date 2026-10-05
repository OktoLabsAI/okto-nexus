CREATE TABLE runtime_execution_grants (
    grant_id TEXT PRIMARY KEY,
    issuer_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    credential_binding TEXT NOT NULL,
    represented_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
    endpoint_id TEXT NOT NULL REFERENCES agent_endpoints(endpoint_id) ON DELETE RESTRICT,
    profile_revision INTEGER,
    actions TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    revision INTEGER NOT NULL DEFAULT 1,
    max_executions INTEGER NOT NULL CHECK (max_executions > 0),
    used_executions INTEGER NOT NULL DEFAULT 0 CHECK (used_executions >= 0),
    created_at TEXT NOT NULL
);
CREATE INDEX idx_runtime_grant_actor ON runtime_execution_grants(actor_agent_id,endpoint_id,revoked_at,expires_at);
CREATE TABLE runtime_access_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    actor_agent_id TEXT,
    action TEXT NOT NULL,
    endpoint_id TEXT,
    session_id TEXT,
    grant_id TEXT,
    grant_revision INTEGER,
    decision TEXT NOT NULL CHECK (decision IN ('allow','deny')),
    created_at TEXT NOT NULL
);
