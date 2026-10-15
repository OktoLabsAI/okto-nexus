-- Conversation response policy never grants competitive handoff authority.
ALTER TABLE runtime_policy_defaults ADD COLUMN broadcast_handoff_auto_claim INTEGER NOT NULL DEFAULT 0
    CHECK(broadcast_handoff_auto_claim IN (0,1));
ALTER TABLE runtime_policy_defaults ADD COLUMN handoff_auto_claim_epoch INTEGER NOT NULL DEFAULT 0
    CHECK(handoff_auto_claim_epoch>=0);
ALTER TABLE agent_runtime_overrides ADD COLUMN broadcast_handoff_auto_claim INTEGER
    CHECK(broadcast_handoff_auto_claim IN (0,1));
ALTER TABLE agent_runtime_overrides ADD COLUMN handoff_auto_claim_epoch INTEGER NOT NULL DEFAULT 0
    CHECK(handoff_auto_claim_epoch>=0);
