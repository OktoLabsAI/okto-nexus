-- Okto Nexus migration 009: per-agent API keys (Nexus v2, spec S1 / FR3-FR4).
-- Forward-only: adds the key columns that make a registered key the primary
-- credential on the HTTP transport (D5 - Pulse policy). Only the SHA256 hash
-- of a key is ever persisted (BR7); the plaintext exists solely in the
-- response of the operation that generated it. `is_active` is the revocation
-- switch: an inactive agent's key must stop authenticating immediately.
-- Backfill: existing V1 agents get api_key_hash = NULL (no key yet; the
-- `okto-nexus admin issue-keys` command emits keys in batch) and
-- is_active = 1 (constant DEFAULT applies to existing rows on ADD COLUMN).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- api_key_hash: lowercase hex SHA256 of the agent's key; NULL while unissued.
ALTER TABLE agents ADD COLUMN api_key_hash TEXT;

-- is_active: revocation flag; 0 disables authentication for the agent's key.
ALTER TABLE agents ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;

-- Partial UNIQUE index: at most one agent per issued key hash (NULLs exempt),
-- and an O(1) lookup path for resolve-by-hash on every authenticated request.
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_api_key_hash
    ON agents (api_key_hash) WHERE api_key_hash IS NOT NULL;
