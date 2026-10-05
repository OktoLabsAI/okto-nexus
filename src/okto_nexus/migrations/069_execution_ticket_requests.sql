-- A lost ticket response cannot be recovered from a stored secret hash.
-- Keep the request identity so replay returns metadata and an explicitly
-- linked successor can replace an unbound credential.
ALTER TABLE execution_link_tickets ADD COLUMN client_intent_id TEXT;
ALTER TABLE execution_link_tickets ADD COLUMN credential_request_id TEXT;
ALTER TABLE execution_link_tickets ADD COLUMN replaces_ticket_id TEXT;
ALTER TABLE execution_link_tickets ADD COLUMN requested_duration_seconds INTEGER;

CREATE UNIQUE INDEX idx_execution_ticket_request
    ON execution_link_tickets(server_id, executor_id, binding_id,
                              agent_id, credential_request_id)
    WHERE credential_request_id IS NOT NULL;
