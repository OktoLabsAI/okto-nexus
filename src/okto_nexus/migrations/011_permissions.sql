-- Okto Nexus migration 011: agent communication permissions + presets.
-- Forward-only. The Pulse permission grammar adapted to the Nexus domain:
-- agents carry an OPTIONAL JSON flags object (NULL = full access, the
-- default-allow rule that keeps every pre-existing agent working), plus an
-- optional preset reference kept for display/reset purposes only -
-- enforcement always reads the agent's own copied flags.
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- permissions: JSON {group: {flag: value}} or NULL (= unrestricted).
ALTER TABLE agents ADD COLUMN permissions TEXT;

-- preset_id: the preset the flags were copied from ('builtin:*' or a custom
-- preset_id); informational - flags are always materialised on the agent row.
ALTER TABLE agents ADD COLUMN preset_id TEXT;

-- Custom permission presets (built-ins live in code and are read-only).
CREATE TABLE IF NOT EXISTS permission_presets (
    preset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    flags TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
