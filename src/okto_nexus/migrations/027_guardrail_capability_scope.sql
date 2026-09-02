-- Okto Nexus migration 027: capability-scoped guardrail assignments.
-- Rebuilds the assignment table because SQLite cannot extend CHECK clauses in
-- place. Existing global/group assignments are preserved with capability NULL.
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

ALTER TABLE guardrail_assignments RENAME TO guardrail_assignments_v25;

CREATE TABLE guardrail_assignments (
    assignment_id TEXT PRIMARY KEY,
    scope_kind TEXT NOT NULL CHECK (scope_kind IN ('global', 'agent_group', 'capability')),
    group_id TEXT REFERENCES agent_groups(group_id),
    capability TEXT REFERENCES capability_names(name),
    guardrail_id TEXT NOT NULL REFERENCES guardrails(guardrail_id),
    version_mode TEXT NOT NULL CHECK (version_mode IN ('latest', 'pinned')),
    pinned_version INTEGER,
    mode TEXT NOT NULL DEFAULT 'audit' CHECK (mode IN ('audit', 'warn', 'enforce')),
    priority INTEGER NOT NULL DEFAULT 100,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT,
    CHECK (
        (scope_kind = 'global' AND group_id IS NULL AND capability IS NULL)
        OR (scope_kind = 'agent_group' AND group_id IS NOT NULL AND capability IS NULL)
        OR (scope_kind = 'capability' AND group_id IS NULL AND capability IS NOT NULL)
    ),
    CHECK ((version_mode = 'latest' AND pinned_version IS NULL) OR (version_mode = 'pinned' AND pinned_version > 0)),
    CHECK (priority >= 0),
    FOREIGN KEY (guardrail_id, pinned_version) REFERENCES guardrail_versions(guardrail_id, version)
);

INSERT INTO guardrail_assignments (
    assignment_id, scope_kind, group_id, capability, guardrail_id,
    version_mode, pinned_version, mode, priority, enabled, created_at, updated_at
)
SELECT assignment_id, scope_kind, group_id, NULL, guardrail_id,
       version_mode, pinned_version, mode, priority, enabled, created_at, updated_at
FROM guardrail_assignments_v25;

DROP TABLE guardrail_assignments_v25;

CREATE INDEX idx_guardrail_assignments_scope ON guardrail_assignments (scope_kind, group_id, capability, enabled, priority);

CREATE INDEX idx_guardrail_assignments_guardrail ON guardrail_assignments (guardrail_id);

CREATE INDEX idx_guardrail_assignments_capability ON guardrail_assignments (capability, enabled, priority);
