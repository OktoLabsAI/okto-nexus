-- Okto Nexus migration 025: communication guardrails and explicit agent groups.
-- Forward-only. Guardrails are table-owned communication rules, separate from
-- governance_policies and attachable policies. Assignments attach a guardrail
-- globally or to an explicit agent group roster. Agent groups are NOT tags and
-- are NOT routing targets; they are concrete memberships only.
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- Explicit rosters of agents for guardrail scoping.
CREATE TABLE IF NOT EXISTS agent_groups (
    group_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_group_members (
    group_id TEXT NOT NULL REFERENCES agent_groups(group_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (group_id, agent_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_group_members_agent ON agent_group_members (agent_id, group_id);

-- Guardrail catalog metadata. Versions live below.
CREATE TABLE IF NOT EXISTS guardrails (
    guardrail_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

-- Versioned evaluator config for one guardrail. Config and targeting columns
-- are JSON TEXT owned by the SQLite adapter:
-- evaluator_config = evaluator-specific object
-- surfaces = ["message", "artifact", "handoff"]
-- field_targets = payload field identifiers evaluated on those surfaces
CREATE TABLE IF NOT EXISTS guardrail_versions (
    guardrail_id TEXT NOT NULL REFERENCES guardrails(guardrail_id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'deprecated', 'archived')),
    evaluator_kind TEXT NOT NULL CHECK (evaluator_kind IN ('deterministic', 'llm')),
    evaluator_config TEXT NOT NULL,
    surfaces TEXT NOT NULL,
    field_targets TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    activated_at TEXT,
    PRIMARY KEY (guardrail_id, version),
    CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS idx_guardrail_versions_status ON guardrail_versions (guardrail_id, status, version);

-- Assignment scope:
-- global: group_id is NULL
-- agent_group: group_id references an explicit roster
-- version_mode latest resolves to max active version at runtime; pinned stores a
-- version number. The repo validates pinned assignments against ACTIVE versions
-- at write time; runtime still treats later inactive pins as config_unavailable.
CREATE TABLE IF NOT EXISTS guardrail_assignments (
    assignment_id TEXT PRIMARY KEY,
    scope_kind TEXT NOT NULL CHECK (scope_kind IN ('global', 'agent_group')),
    group_id TEXT REFERENCES agent_groups(group_id),
    guardrail_id TEXT NOT NULL REFERENCES guardrails(guardrail_id),
    version_mode TEXT NOT NULL CHECK (version_mode IN ('latest', 'pinned')),
    pinned_version INTEGER,
    mode TEXT NOT NULL CHECK (mode IN ('audit', 'warn', 'enforce')),
    priority INTEGER NOT NULL DEFAULT 100,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT,
    CHECK ((scope_kind = 'global' AND group_id IS NULL) OR (scope_kind = 'agent_group' AND group_id IS NOT NULL)),
    CHECK ((version_mode = 'latest' AND pinned_version IS NULL) OR (version_mode = 'pinned' AND pinned_version > 0)),
    CHECK (priority >= 0),
    FOREIGN KEY (guardrail_id, pinned_version) REFERENCES guardrail_versions(guardrail_id, version)
);

CREATE INDEX IF NOT EXISTS idx_guardrail_assignments_scope ON guardrail_assignments (scope_kind, group_id, enabled, priority);

CREATE INDEX IF NOT EXISTS idx_guardrail_assignments_guardrail ON guardrail_assignments (guardrail_id);
