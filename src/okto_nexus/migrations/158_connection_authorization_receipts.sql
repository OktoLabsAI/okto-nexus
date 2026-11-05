-- Reviewed grant issuance uses the canonical grant table, with an atomic receipt.
CREATE TABLE connection_authorization_receipts (
    actor_agent_id TEXT NOT NULL,
    client_request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (actor_agent_id, client_request_id)
);
