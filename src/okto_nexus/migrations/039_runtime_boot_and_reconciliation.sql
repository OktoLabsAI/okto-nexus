CREATE TABLE runtime_boot_bindings (
    endpoint_id TEXT PRIMARY KEY REFERENCES agent_endpoints(endpoint_id) ON DELETE RESTRICT,
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    endpoint_revision INTEGER NOT NULL,
    profile_revision INTEGER,
    issuer_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    issuer_credential_binding TEXT,
    revision INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);
CREATE TABLE runtime_endpoint_reconciliations (
    reconciliation_id TEXT PRIMARY KEY,
    endpoint_id TEXT NOT NULL REFERENCES agent_endpoints(endpoint_id) ON DELETE RESTRICT,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    reason TEXT NOT NULL,
    prior_health TEXT NOT NULL,
    prior_reason TEXT,
    endpoint_revision INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(actor_agent_id,idempotency_key)
);
ALTER TABLE runtime_open_requests ADD COLUMN boot_revision INTEGER;
ALTER TABLE runtime_open_requests ADD COLUMN effects_started INTEGER NOT NULL DEFAULT 0 CHECK(effects_started IN (0,1));
