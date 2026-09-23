ALTER TABLE handoffs ADD COLUMN claim_epoch INTEGER NOT NULL DEFAULT 0 CHECK (claim_epoch >= 0);
UPDATE handoffs SET claim_epoch = 1 WHERE claimed_by IS NOT NULL;
