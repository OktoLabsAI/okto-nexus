-- Okto Nexus core schema (migration 001).
-- SQLite is the single source of truth. Every coordinated entity is scoped by
-- workspace_id (NOT NULL + FK). Timestamps are UTC ISO-8601 TEXT. JSON-ish
-- columns (payload/capabilities/metadata/artifacts) are stored as TEXT.
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- Applied-migration ledger.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Workspaces: keyed by deterministic workspace_id = sha256(realpath(root)).
CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    display_name TEXT,
    root_realpath TEXT,
    created_at TEXT NOT NULL,
    last_seen_at TEXT
);

-- Agents: global logical identities (not workspace-scoped).
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    role TEXT,
    capabilities TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL
);

-- Sessions: a live agent bound to a workspace.
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    last_heartbeat_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_workspace ON sessions (workspace_id, status);

CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions (workspace_id, agent_id);

-- Events: append-only, immutable log. event_id is global & monotonic.
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    stream TEXT NOT NULL,
    type TEXT NOT NULL,
    actor_agent_id TEXT,
    payload TEXT,
    visibility TEXT,
    target TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_workspace ON events (workspace_id, event_id);

CREATE INDEX IF NOT EXISTS idx_events_stream ON events (workspace_id, stream, event_id);

-- Channels: named message channels, unique per (workspace, name).
CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, name)
);

CREATE INDEX IF NOT EXISTS idx_channels_workspace ON channels (workspace_id, name);

-- Messages: posted to a channel and/or directed at a target.
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    channel_id TEXT REFERENCES channels(channel_id),
    from_agent_id TEXT NOT NULL,
    from_session_id TEXT,
    target TEXT,
    subject TEXT,
    body TEXT,
    artifacts TEXT,
    parent_message_id TEXT REFERENCES messages(message_id),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_workspace ON messages (workspace_id, created_at);

CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages (workspace_id, channel_id, created_at);

-- Tasks: units of work tracked within a workspace.
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON tasks (workspace_id, status);

-- Handoffs: claimable transfers of work, optionally linked to a task.
CREATE TABLE IF NOT EXISTS handoffs (
    handoff_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    task_id TEXT REFERENCES tasks(task_id),
    from_agent_id TEXT,
    target TEXT,
    visibility TEXT,
    status TEXT NOT NULL,
    claimed_by TEXT,
    lease_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_handoffs_workspace ON handoffs (workspace_id, status);

CREATE INDEX IF NOT EXISTS idx_handoffs_target ON handoffs (workspace_id, target, status);

-- Artifacts: inline content or workspace-relative path references.
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    artifact_type TEXT NOT NULL,
    name TEXT,
    path TEXT,
    content TEXT,
    size_bytes INTEGER,
    content_type TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_workspace ON artifacts (workspace_id, artifact_type);
