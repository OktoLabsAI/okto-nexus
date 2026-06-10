-- Okto Nexus migration 006: inbox delivery hardening (M4+M8).
-- Forward-only. Adds the per-delivery claim counter that backs the 'parked'
-- (dead-letter) lane: every successful claim of a delivery increments
-- attempts; once a delivery has been claimed the maximum number of times and
-- becomes claimable again, the claim parks it (status 'parked') instead of
-- redelivering forever - a poison message stops reoccupying the head of every
-- pull batch. The status column is plain TEXT, so the new 'parked' value
-- needs no schema change; only this counter does. Idempotency is guaranteed
-- at the runner level (schema_migrations ledger records version 006 once).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

ALTER TABLE message_deliveries ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;

-- Inbox history pagination is keyset ((read_at, delivery_id) descending) per
-- recipient; this index serves those pages without a scan-and-sort.
CREATE INDEX IF NOT EXISTS idx_deliveries_history ON message_deliveries (recipient_agent_id, status, read_at DESC, delivery_id DESC);
