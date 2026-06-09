-- Okto Nexus migration 004: agent last-seen tracking.
-- Forward-only: adds last_seen_at to agents so every agent operation can stamp
-- the agent's most recent interaction with the bus, surfaced by agent_list and
-- agent_get. Idempotency is guaranteed at the runner level (schema_migrations
-- ledger records version 004 once).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- last_seen_at: UTC ISO-8601 TEXT of the agent's most recent action, NULL until
-- the agent first acts after being registered.
ALTER TABLE agents ADD COLUMN last_seen_at TEXT;
