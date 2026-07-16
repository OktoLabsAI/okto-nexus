-- Okto Nexus migration 014: central capability catalog.
-- Forward-only. Capabilities stop being free-form text: this GLOBAL registry
-- (mirror of tag_keys from migration 013, WITHOUT a values table - capability
-- names are a flat list) is the single vocabulary every write path validates
-- against FAIL-CLOSED at the application layer (agent capabilities and
-- {strategy: "capability"} targets, including sub-rules inside "mixed").
-- The transition never breaks an existing agent: the Python bootstrap seeds
-- this table idempotently (insert-or-ignore) with every capability already
-- announced by ANY persisted agent (normalize_capabilities is the single
-- normalisation rule and lives in Python, so the seed is NOT done in SQL).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

CREATE TABLE IF NOT EXISTS capability_names (
    name TEXT PRIMARY KEY,
    description TEXT,
    created_at TEXT NOT NULL
);
