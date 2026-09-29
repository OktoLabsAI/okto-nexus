-- R4 agent-scoped revision ledger. No legacy identity or permission is changed.
CREATE TABLE execution_agent_revisions (
    server_id TEXT NOT NULL,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    authorization_revision INTEGER NOT NULL CHECK (authorization_revision >= 1),
    configuration_revision INTEGER NOT NULL CHECK (configuration_revision >= 1),
    credential_epoch INTEGER NOT NULL CHECK (credential_epoch >= 1),
    authorization_digest TEXT NOT NULL,
    configuration_digest TEXT NOT NULL,
    credential_digest TEXT NOT NULL,
    PRIMARY KEY (server_id,agent_id)
);
