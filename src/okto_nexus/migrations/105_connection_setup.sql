-- Idempotent, atomic Finish receipts. Draft tests never activate a connection.
CREATE TABLE connection_setup_commits (
    actor_agent_id TEXT NOT NULL,
    client_intent_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (actor_agent_id, client_intent_id)
);
