ALTER TABLE message_deliveries ADD COLUMN consumer_kind TEXT CHECK (consumer_kind IN ('pull','push'));
ALTER TABLE message_deliveries ADD COLUMN consumer_operation_id TEXT;
CREATE TABLE delivery_outbox (
    operation_id TEXT PRIMARY KEY,
    delivery_id TEXT NOT NULL UNIQUE REFERENCES message_deliveries(delivery_id) ON DELETE RESTRICT,
    message_id TEXT NOT NULL REFERENCES messages(message_id) ON DELETE RESTRICT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    credential_binding TEXT NOT NULL,
    recipient_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    endpoint_id TEXT NOT NULL REFERENCES agent_endpoints(endpoint_id) ON DELETE RESTRICT,
    endpoint_revision INTEGER NOT NULL,
    profile_revision INTEGER,
    runtime_session_id TEXT REFERENCES harness_sessions(session_id) ON DELETE RESTRICT,
    envelope TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    authorization_revision TEXT NOT NULL,
    root_operation_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','CLAIMED','SENDING','ACCEPTED','SENT_UNCONFIRMED','OUTCOME_UNKNOWN','RETRY_WAIT','REJECTED','CANCELLED','FAILED_FINAL')),
    owner_epoch INTEGER,
    attempt_id TEXT,
    lease_expires_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    ack_level TEXT NOT NULL DEFAULT 'NONE',
    reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_runtime_outbox_pending ON delivery_outbox(status,created_at,operation_id);
CREATE INDEX idx_runtime_outbox_endpoint ON delivery_outbox(endpoint_id,status);
CREATE INDEX idx_delivery_consumer ON message_deliveries(recipient_agent_id,consumer_kind,status);
CREATE TABLE runtime_dispatcher_owner (
    owner_key TEXT PRIMARY KEY CHECK (owner_key='dispatcher'),
    epoch INTEGER NOT NULL,
    owner_id TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL
);
CREATE TABLE runtime_open_requests (
    request_id TEXT PRIMARY KEY,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RESERVED','COMPLETED','FAILED_FINAL','OUTCOME_UNKNOWN')),
    created_at TEXT NOT NULL,
    UNIQUE(actor_agent_id,idempotency_key)
);
ALTER TABLE harness_sessions ADD COLUMN open_request_id TEXT REFERENCES runtime_open_requests(request_id) ON DELETE RESTRICT;
ALTER TABLE harness_sessions ADD COLUMN runtime_profile_revision INTEGER;
CREATE UNIQUE INDEX idx_harness_open_request ON harness_sessions(open_request_id);
