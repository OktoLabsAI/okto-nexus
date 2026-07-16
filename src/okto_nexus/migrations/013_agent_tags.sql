-- Okto Nexus migration 013: agent tags + communication scope + tag catalog.
-- Forward-only. Tag-based communication scoping (phase F1): agents carry an
-- OPTIONAL multi-value tag map plus an OPTIONAL operator-set communication
-- scope; both are JSON TEXT columns (NULL = absent = default-allow, keeping
-- every pre-existing agent working unchanged).
-- Tags are NOT free-form: the central catalog below (tag_keys/tag_values) is
-- the single registry - key AND value existence is validated FAIL-CLOSED at
-- the application layer before anything references them.
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- tags: JSON {key: [value, ...]} or NULL (= no tags). Exposed on discovery.
ALTER TABLE agents ADD COLUMN tags TEXT;

-- comm_scope: JSON {"outbound": <selector or null>} or NULL (= unrestricted).
-- Operator-only and PRIVATE: never exposed on any discovery surface.
ALTER TABLE agents ADD COLUMN comm_scope TEXT;

-- Central tag catalog: registered keys...
CREATE TABLE IF NOT EXISTS tag_keys (
    key TEXT PRIMARY KEY,
    description TEXT,
    created_at TEXT NOT NULL
);

-- ...and their registered values (a value exists only under its key; deleting
-- an UNUSED key removes its values with it - in-use deletion is blocked at
-- the application layer with TAG_IN_USE before this cascade can run).
CREATE TABLE IF NOT EXISTS tag_values (
    key TEXT NOT NULL REFERENCES tag_keys(key) ON DELETE CASCADE,
    value TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (key, value)
);
