-- Okto Nexus migration 026: ephemeral poll tokens for remote monitors.
-- Forward-only. Poll tokens are short-lived, read-only bearer credentials
-- issued from an authenticated MCP session. Only their SHA-256 hash is stored.
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

CREATE TABLE IF NOT EXISTS ephemeral_poll_tokens (
    token_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    issue_cursor INTEGER NOT NULL DEFAULT 0 CHECK (issue_cursor >= 0),
    scope TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    renewed_at TEXT,
    last_used_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ept_active_agent_workspace
ON ephemeral_poll_tokens (agent_id, workspace_id)
WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_ept_hash
ON ephemeral_poll_tokens (token_hash);

CREATE INDEX IF NOT EXISTS idx_ept_session
ON ephemeral_poll_tokens (session_id, revoked_at);
