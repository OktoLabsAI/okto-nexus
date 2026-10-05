-- Preserve the policy decision made at canonical creation, not a later
-- policy snapshot adopted by the first transport attempt. No legacy backfill:
-- an old handoff is not proof of an approval under current policies.
CREATE TABLE handoff_authorization_receipts (
    handoff_id TEXT PRIMARY KEY REFERENCES handoffs(handoff_id) ON DELETE CASCADE,
    creator_policy_revision TEXT NOT NULL,
    hitl_enabled INTEGER NOT NULL CHECK(hitl_enabled IN (0,1)),
    created_at TEXT NOT NULL
);
