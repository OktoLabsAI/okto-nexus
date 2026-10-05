-- Expand policies without rebuilding endpoint foreign keys or removing guards.
ALTER TABLE agent_endpoints ADD COLUMN session_policy_next TEXT NOT NULL DEFAULT 'shared'
    CHECK(session_policy_next IN ('shared','per_sender','per_sender_session'));
UPDATE agent_endpoints SET session_policy_next=session_policy;
ALTER TABLE agent_endpoints DROP COLUMN session_policy;
ALTER TABLE agent_endpoints RENAME COLUMN session_policy_next TO session_policy;

ALTER TABLE runtime_policy_defaults ADD COLUMN session_policy_next TEXT NOT NULL DEFAULT 'shared'
    CHECK(session_policy_next IN ('shared','per_sender','per_sender_session'));
UPDATE runtime_policy_defaults SET session_policy_next=session_policy;
ALTER TABLE runtime_policy_defaults DROP COLUMN session_policy;
ALTER TABLE runtime_policy_defaults RENAME COLUMN session_policy_next TO session_policy;

ALTER TABLE agent_runtime_overrides ADD COLUMN session_policy_next TEXT
    CHECK(session_policy_next IN ('shared','per_sender','per_sender_session'));
UPDATE agent_runtime_overrides SET session_policy_next=session_policy;
ALTER TABLE agent_runtime_overrides DROP COLUMN session_policy;
ALTER TABLE agent_runtime_overrides RENAME COLUMN session_policy_next TO session_policy;

ALTER TABLE execution_sender_sessions ADD COLUMN isolation_policy TEXT NOT NULL DEFAULT 'per_sender'
    CHECK(isolation_policy IN ('per_sender','per_sender_session'));
ALTER TABLE execution_sender_sessions ADD COLUMN source_session_key TEXT NOT NULL DEFAULT '';

-- Internal provenance, never a user-supplied routing field or credential.
-- An absent row means the sender has no verified session (including operator UI).
CREATE TABLE execution_message_origins (
    message_id TEXT PRIMARY KEY REFERENCES messages(message_id),
    source_session_key TEXT NOT NULL
);
