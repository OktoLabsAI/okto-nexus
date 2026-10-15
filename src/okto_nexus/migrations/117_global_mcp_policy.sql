ALTER TABLE runtime_policy_defaults ADD COLUMN inherit_global_mcps INTEGER NOT NULL DEFAULT 0 CHECK(inherit_global_mcps IN (0,1));
ALTER TABLE agent_runtime_overrides ADD COLUMN inherit_global_mcps INTEGER CHECK(inherit_global_mcps IN (0,1));
