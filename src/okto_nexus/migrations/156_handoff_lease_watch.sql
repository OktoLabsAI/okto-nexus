-- Lease watch for claimed handoffs (#92).
-- The partial index lets the 5 s scheduler sweep find due leases with one probe.
CREATE INDEX IF NOT EXISTS idx_handoffs_claimed_lease
    ON handoffs (lease_expires_at) WHERE status = 'CLAIMED';

-- One row per claim epoch that already got a silence warning.
CREATE TABLE IF NOT EXISTS handoff_silence_notices (
    handoff_id  TEXT NOT NULL,
    claim_epoch INTEGER NOT NULL,
    notified_at TEXT NOT NULL,
    PRIMARY KEY (handoff_id, claim_epoch)
) WITHOUT ROWID;
