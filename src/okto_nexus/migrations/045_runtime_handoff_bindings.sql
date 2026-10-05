CREATE TABLE runtime_handoff_bindings (
    handoff_id TEXT NOT NULL REFERENCES handoffs(handoff_id) ON DELETE RESTRICT,
    claim_epoch INTEGER NOT NULL CHECK (claim_epoch > 0),
    operation_id TEXT NOT NULL UNIQUE REFERENCES delivery_outbox(operation_id) ON DELETE RESTRICT,
    grant_id TEXT NOT NULL REFERENCES runtime_execution_grants(grant_id) ON DELETE RESTRICT,
    grant_revision INTEGER NOT NULL,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(handoff_id, claim_epoch),
    UNIQUE(actor_agent_id, idempotency_key)
);
CREATE INDEX idx_runtime_work_grant ON runtime_handoff_bindings(grant_id);
