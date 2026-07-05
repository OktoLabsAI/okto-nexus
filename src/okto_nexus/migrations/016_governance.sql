-- Okto Nexus migration 016: governance policies (deny rules + quotas).
-- Forward-only. V1 of the policy engine (spec ffef15bf): the operator declares
-- deny-only policies - subject (agent | role | capability | star) x action
-- (message_create, broadcast, handoff_create, artifact_put) x limit (deny,
-- max_count per 1h/24h sliding window, max_bytes, max_open_handoffs).
-- Policies are GLOBAL (no workspace_id - V1 decision; a workspace column is an
-- additive V2 change). Sliding windows are derived ON-DEMAND from the existing
-- tables inside the write path's own UoW (never a counter table), which is why
-- this migration also adds the per-agent time indexes below.
-- The column is named time_window (not "window") to stay clear of the SQLite
-- WINDOW keyword; the external contract field is still called "window".
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

CREATE TABLE IF NOT EXISTS governance_policies (
    policy_id TEXT PRIMARY KEY,
    subject_kind TEXT NOT NULL,
    subject_value TEXT,
    action TEXT NOT NULL,
    limit_kind TEXT NOT NULL,
    limit_value INTEGER,
    time_window TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

-- Authorship for artifacts: the 001 schema has no author column, but the
-- artifact_put quota (max_count per agent) needs one. Additive, no backfill:
-- legacy rows stay NULL and simply never count against any agent.
ALTER TABLE artifacts ADD COLUMN created_by TEXT;

-- Per-agent time indexes so on-demand window COUNTs are cheap. Consumption is
-- GLOBAL per agent (no workspace_id in the key - matches messages.count_since).
CREATE INDEX IF NOT EXISTS idx_messages_agent_time ON messages (from_agent_id, created_at);

CREATE INDEX IF NOT EXISTS idx_handoffs_agent_time ON handoffs (from_agent_id, created_at);

CREATE INDEX IF NOT EXISTS idx_artifacts_agent_time ON artifacts (created_by, created_at);
