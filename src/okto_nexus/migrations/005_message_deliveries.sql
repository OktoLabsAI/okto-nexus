-- Okto Nexus migration 005: message inbox delivery (ADR 0001).
-- Forward-only: per-recipient delivery lanes (unread/delivered/read) for the
-- inbox model. GLOBAL (deliberately NOT workspace-scoped): an agent's inbox
-- spans every workspace, so a direct message reaches the recipient regardless of
-- where the sender posted. Idempotency is guaranteed at the runner level
-- (schema_migrations ledger records version 005 once).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- One row per (message, recipient). status: 'unread' (queued) -> 'delivered'
-- (pulled, in-flight under a lease) -> 'read' (acknowledged into history).
CREATE TABLE IF NOT EXISTS message_deliveries (
    delivery_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(message_id),
    recipient_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    status TEXT NOT NULL,
    delivered_at TEXT,
    lease_expires_at TEXT,
    read_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (message_id, recipient_agent_id)
);

-- Inbox lookups are by recipient + status (unread / in-flight scans).
CREATE INDEX IF NOT EXISTS idx_deliveries_inbox ON message_deliveries (recipient_agent_id, status);

-- Lease-expiry sweep scans in-flight rows by their lease deadline.
CREATE INDEX IF NOT EXISTS idx_deliveries_lease ON message_deliveries (status, lease_expires_at);
