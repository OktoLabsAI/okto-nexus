-- Okto Nexus migration 018: handoff verification (I4).
-- Forward-only, additive: adds the opt-in verification columns to handoffs.
-- NULL means "not verifiable" - both pre-018 rows and new handoffs created
-- without acceptance_criteria keep the plain CLAIMED -> COMPLETED flow, so
-- existing data needs no backfill. Values are serialised TEXT written by the
-- application layer (JSON for the list/descriptor; the repo treats them
-- opaquely, same contract as `payload`/`result`).
-- Idempotency is guaranteed at the runner level (schema_migrations ledger
-- records version 018 once).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- acceptance_criteria: JSON list of 1..20 criteria strings captured at
-- handoff_create (NULL = verification not requested).
ALTER TABLE handoffs ADD COLUMN acceptance_criteria TEXT;

-- verify_by: JSON descriptor {"kind": creator|agent|capability, ...} chosen at
-- handoff_create; the creator default is MATERIALISED at write time, so a
-- verifiable row always carries an explicit descriptor.
ALTER TABLE handoffs ADD COLUMN verify_by TEXT;

-- verification_feedback: free-text rework guidance written ONLY by a "fail"
-- verdict; each fail overwrites it (including back to NULL) so the column
-- always reflects the LATEST fail - history lives in the event log.
ALTER TABLE handoffs ADD COLUMN verification_feedback TEXT;
