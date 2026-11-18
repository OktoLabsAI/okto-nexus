CREATE TABLE session_attachment_epochs (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    writer_epoch INTEGER NOT NULL CHECK (writer_epoch >= 0),
    PRIMARY KEY (server_id, executor_id, session_id),
    FOREIGN KEY (server_id, executor_id, session_id)
        REFERENCES execution_sessions(server_id, executor_id, session_id)
);

CREATE TABLE session_attachments (
    attachment_id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    scope_hash TEXT NOT NULL,
    authority_ref TEXT NOT NULL,
    surface TEXT NOT NULL,
    client_intent_id TEXT NOT NULL,
    intent_hash TEXT NOT NULL,
    broker_instance TEXT NOT NULL,
    capability_revision TEXT NOT NULL,
    audience TEXT NOT NULL,
    access TEXT NOT NULL CHECK (access IN ('read', 'write')),
    expected_writer_epoch INTEGER,
    takeover INTEGER NOT NULL CHECK (takeover IN (0, 1)),
    writer_epoch INTEGER,
    state TEXT NOT NULL CHECK (state IN ('PREPARED', 'CHALLENGE', 'ACTIVE', 'DETACHED', 'EXPIRED', 'REPLACED')),
    ticket_hash TEXT,
    challenge_hash TEXT,
    channel_id TEXT,
    expires_monotonic REAL NOT NULL,
    UNIQUE (server_id, executor_id, session_id, scope_hash, authority_ref, surface, client_intent_id),
    FOREIGN KEY (server_id, executor_id, session_id)
        REFERENCES execution_sessions(server_id, executor_id, session_id)
);

CREATE UNIQUE INDEX session_attachment_one_writer
    ON session_attachments(server_id, executor_id, session_id)
    WHERE state='ACTIVE' AND access='write';
CREATE INDEX session_attachments_active
    ON session_attachments(server_id, executor_id, session_id, state);
