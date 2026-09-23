-- An operator decision about a transport attempt is not native acceptance.
CREATE TABLE runtime_operation_reconciliations (
    reconciliation_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    source_kind TEXT NOT NULL CHECK(source_kind IN ('delivery_outbox','runtime_commands')),
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('cancel_pending','release_to_inbox','abandon_command')),
    previous_state TEXT NOT NULL,
    attempt_id TEXT,
    owner_epoch INTEGER,
    endpoint_id TEXT NOT NULL REFERENCES agent_endpoints(endpoint_id) ON DELETE RESTRICT,
    duplicate_risk_acknowledged INTEGER NOT NULL CHECK(duplicate_risk_acknowledged IN (0,1)),
    reason TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(actor_agent_id,idempotency_key)
);
ALTER TABLE delivery_outbox ADD COLUMN reconciliation_id TEXT REFERENCES runtime_operation_reconciliations(reconciliation_id) ON DELETE RESTRICT;
ALTER TABLE runtime_commands ADD COLUMN reconciliation_id TEXT REFERENCES runtime_operation_reconciliations(reconciliation_id) ON DELETE RESTRICT;
CREATE INDEX idx_runtime_reconciliation_endpoint ON runtime_operation_reconciliations(endpoint_id,created_at);
CREATE INDEX idx_runtime_outbox_unresolved ON delivery_outbox(endpoint_id,status,created_at,operation_id) WHERE reconciliation_id IS NULL;
CREATE INDEX idx_runtime_commands_unresolved ON runtime_commands(endpoint_id,status,created_at,operation_id) WHERE reconciliation_id IS NULL;
