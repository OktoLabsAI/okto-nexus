-- Only the active Server publishes effective process policy. Stored settings
-- and migration defaults are not evidence of which policy a Server applied.
CREATE TABLE server_effective_policy (
    key TEXT PRIMARY KEY NOT NULL
        CHECK (key IN ('feature_harness_integrations', 'feature_hitl')),
    value INTEGER NOT NULL CHECK (typeof(value) = 'integer' AND value IN (0, 1)),
    generation INTEGER NOT NULL CHECK (typeof(generation) = 'integer' AND generation >= 1),
    changed_at TEXT NOT NULL
);
