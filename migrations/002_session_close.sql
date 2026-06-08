-- Okto Nexus migration 002: session close support.
-- Forward-only: adds the closed_at timestamp column to sessions so a session
-- can be explicitly closed (status='closed' + closed_at). Idempotency is
-- guaranteed at the runner level (schema_migrations ledger records version 002
-- once); this migration is never re-applied to a database that already has it.
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- closed_at: UTC ISO-8601 TEXT, NULL until the session is closed.
ALTER TABLE sessions ADD COLUMN closed_at TEXT;
