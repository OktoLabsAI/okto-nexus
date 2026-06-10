-- Okto Nexus migration 008: handoff outcome persistence.
-- Forward-only: adds the terminal-outcome columns to handoffs so the creator
-- can READ the result of a finished handoff by id (handoff_get) instead of
-- scanning the event stream (events are observability, not delivery; a
-- terminal handoff also disappears from handoff_list_available). Same opaque
-- semantics as `payload`: a string is stored verbatim, a non-string value is
-- serialised to JSON TEXT; both are subject to the 64KB inclusive inline
-- limit enforced by the application layer. Idempotency is guaranteed at the
-- runner level (schema_migrations ledger records version 008 once).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- result: the completion outcome recorded by handoff_complete (NULL until the
-- handoff is COMPLETED with an inline result).
ALTER TABLE handoffs ADD COLUMN result TEXT;

-- rejected_reason: the reason recorded by handoff_reject (NULL until the
-- handoff is REJECTED with an inline reason).
ALTER TABLE handoffs ADD COLUMN rejected_reason TEXT;
