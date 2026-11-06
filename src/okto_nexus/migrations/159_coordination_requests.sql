-- Canonical references survive resource/approval pruning during the 30-day
-- replay window. Deliberately no cascading FK to the referenced objects.
-- Payloads, raw credentials and authorization decisions are not copied here.
CREATE TABLE coordination_requests (
    server_id TEXT NOT NULL,
    actor_agent_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('message_create', 'handoff_create')),
    client_request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('created', 'pending_approval')),
    resource_id TEXT,
    approval_id TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL CHECK (expires_at > created_at),
    PRIMARY KEY (server_id, actor_agent_id, workspace_id, operation, client_request_id),
    CHECK ((state = 'created' AND resource_id IS NOT NULL)
        OR (state = 'pending_approval' AND resource_id IS NULL AND approval_id IS NOT NULL))
);
CREATE INDEX idx_coordination_requests_expiry ON coordination_requests(expires_at);
CREATE UNIQUE INDEX idx_coordination_requests_approval ON coordination_requests(server_id, approval_id)
    WHERE approval_id IS NOT NULL;
