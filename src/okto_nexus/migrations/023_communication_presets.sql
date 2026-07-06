-- Okto Nexus migration 023: communication presets (spec 6f961722).
-- Forward-only, ADDITIVE, NO backfill (D-CP-8). A communication preset is a 4th
-- per-agent axis - ORTHOGONAL to comm_scope (WHO an agent may reach),
-- permissions (WHAT it may do) and policies (audience+governance). It carries a
-- self-descriptive COMMUNICATION STYLE (tone/format/language/verbosity/structure
-- + free-text additional_instructions) surfaced SELF-ONLY on whoami, telling the
-- agent HOW it should communicate. Presets are GLOBAL (no workspace_id - the
-- same V1 decision as policies/governance/tag_keys/capabilities).
-- Cardinality DIVERGES from policies (D-CP-2): a preset binding is SINGLE-SOURCE
-- (inline XOR one global reference), never composed - so the binding table is
-- keyed by agent_id alone (at most one row per agent). An agent with NO binding
-- keeps today's whoami byte-for-byte (zero regression, D-CP-6).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- Catalog of NAMED global presets (metadata only; versions live below).
CREATE TABLE IF NOT EXISTS comm_presets (
    preset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

-- Append-only versions of each global preset. content is JSON TEXT: an object
-- of the CLOSED dimension keys (tone/format/language/verbosity/structure +
-- additional_instructions) with FREE string values; an empty object is valid.
-- A version is IMMUTABLE once published; editing publishes a new (preset_id,
-- version) row. Deleting the catalog row cascades its versions.
CREATE TABLE IF NOT EXISTS comm_preset_versions (
    preset_id TEXT NOT NULL REFERENCES comm_presets(preset_id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    published_at TEXT NOT NULL,
    PRIMARY KEY (preset_id, version)
);

-- Per-agent binding, SINGLE-SOURCE (agent_id is the PRIMARY KEY, so at most one
-- row per agent - the inline-XOR-global cardinality is a table invariant, not a
-- guard). source='inline' embeds content (preset_id/mode/pinned_version NULL);
-- source='global' references a preset (preset_id + mode in {latest,pinned};
-- pinned_version set only for pinned; content NULL). The preset_id FK (NULL for
-- inline) keeps a binding from referencing a missing preset; deletion of an
-- in-use preset is blocked upstream (COMM_PRESET_IN_USE) before this FK fires.
-- Bindings cascade when their agent is deleted.
CREATE TABLE IF NOT EXISTS agent_comm_binding (
    agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    preset_id TEXT REFERENCES comm_presets(preset_id),
    mode TEXT,
    pinned_version INTEGER,
    content TEXT,
    created_at TEXT NOT NULL
);

-- Reverse index for the COMM_PRESET_IN_USE guard (which agents bind a preset).
CREATE INDEX IF NOT EXISTS idx_agent_comm_binding_preset ON agent_comm_binding (preset_id);
