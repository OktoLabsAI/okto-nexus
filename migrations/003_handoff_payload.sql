-- Okto Nexus migration 003: handoff payload passthrough.
-- Forward-only: adds the payload column to handoffs so the request body travels
-- WITH the row and is returned by handoff_list_available / handoff_claim,
-- removing the friction of correlating the handoff.created event just to read
-- the work content. Idempotency is guaranteed at the runner level
-- (schema_migrations ledger records version 003 once).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- payload: opaque inline request content (TEXT; a JSON string or a free string),
-- NULL when the handoff carries no inline payload. Subject to the 64KB inclusive
-- inline limit enforced by the application layer.
ALTER TABLE handoffs ADD COLUMN payload TEXT;
