-- A pre-admission ledger. Canonical effects still belong to R4 operations.
CREATE TABLE session_interaction_queues (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    next_sequence INTEGER NOT NULL CHECK (typeof(next_sequence) = 'integer' AND next_sequence >= 1),
    revision INTEGER NOT NULL CHECK (typeof(revision) = 'integer' AND revision >= 0),
    PRIMARY KEY (server_id, executor_id, session_id),
    FOREIGN KEY (server_id, executor_id, session_id)
        REFERENCES execution_sessions(server_id, executor_id, session_id)
);

CREATE TABLE session_interaction_inputs (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    owner_generation INTEGER NOT NULL CHECK (owner_generation >= 1),
    binding_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    workspace_binding_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    input_id TEXT NOT NULL,
    authority_ref TEXT NOT NULL,
    surface TEXT NOT NULL CHECK (surface IN ('web', 'nexus_cli', 'native_terminal')),
    client_intent_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    enqueue_sequence INTEGER NOT NULL CHECK (enqueue_sequence >= 1),
    input_revision INTEGER NOT NULL DEFAULT 0 CHECK (input_revision >= 0),
    capability_revision TEXT NOT NULL,
    content TEXT NOT NULL CHECK (length(CAST(content AS BLOB)) BETWEEN 1 AND 65536),
    status TEXT NOT NULL CHECK (status IN (
        'QUEUED', 'DISPATCHING', 'ACCEPTED_NATIVE', 'REFUSED_BEFORE_SEND', 'DELIVERY_UNKNOWN',
        'BLOCKED_AUTH', 'BLOCKED_SESSION', 'PAUSED', 'EXPIRED', 'CANCELLED'
    )),
    operation_id TEXT,
    possible_effect INTEGER NOT NULL DEFAULT 0 CHECK (possible_effect IN (0, 1)),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (server_id, executor_id, session_id, input_id),
    UNIQUE (server_id, executor_id, session_id, authority_ref, client_intent_id),
    UNIQUE (server_id, executor_id, session_id, enqueue_sequence),
    UNIQUE (server_id, executor_id, operation_id),
    FOREIGN KEY (server_id, executor_id, session_id)
        REFERENCES session_interaction_queues(server_id, executor_id, session_id),
    FOREIGN KEY (server_id, executor_id, operation_id)
        REFERENCES execution_operations(server_id, executor_id, operation_id),
    CHECK (status NOT IN ('DISPATCHING', 'ACCEPTED_NATIVE', 'DELIVERY_UNKNOWN') OR operation_id IS NOT NULL),
    CHECK (status <> 'DELIVERY_UNKNOWN' OR possible_effect = 1),
    CHECK (possible_effect = 0 OR status IN ('DISPATCHING', 'ACCEPTED_NATIVE', 'DELIVERY_UNKNOWN'))
);

CREATE INDEX idx_session_inputs_pending ON session_interaction_inputs(
    server_id, executor_id, session_id, status, enqueue_sequence
);
