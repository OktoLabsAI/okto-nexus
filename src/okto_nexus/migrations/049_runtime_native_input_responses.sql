-- Explicit private human response, committed atomically with canonical decision.
-- NULL preserves binary approvals and requests without a decision.
ALTER TABLE runtime_native_approvals ADD COLUMN response_payload TEXT;
