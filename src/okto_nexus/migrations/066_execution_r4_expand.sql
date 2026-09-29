-- R4 additive execution state. No legacy row or policy is rewritten here.
CREATE TABLE execution_installation (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    server_id TEXT NOT NULL UNIQUE,
    embedded_executor_id TEXT NOT NULL UNIQUE,
    schema_revision INTEGER NOT NULL CHECK (schema_revision >= 1),
    created_at TEXT NOT NULL
);

CREATE TABLE execution_executors (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    connector_id TEXT,
    registered_by_agent_id TEXT REFERENCES agents(agent_id),
    kind TEXT NOT NULL CHECK (kind IN ('embedded','remote')),
    label TEXT,
    control_state TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    owner_instance_id TEXT,
    last_seen_at TEXT,
    revoked_at TEXT,
    CHECK ((kind = 'embedded' AND connector_id IS NULL AND registered_by_agent_id IS NULL) OR
           (kind = 'remote' AND connector_id IS NOT NULL AND registered_by_agent_id IS NOT NULL)),
    PRIMARY KEY (server_id, executor_id),
    UNIQUE (server_id, kind, connector_id)
);
CREATE INDEX idx_execution_executors_state ON execution_executors(server_id,control_state,last_seen_at);

CREATE TABLE execution_workspace_bindings (
    server_id TEXT NOT NULL,
    workspace_binding_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    realization_handle TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    local_label TEXT,
    status TEXT NOT NULL,
    PRIMARY KEY (server_id, workspace_binding_id),
    UNIQUE (server_id, executor_id, workspace_binding_id),
    FOREIGN KEY (server_id, executor_id) REFERENCES execution_executors(server_id,executor_id)
);
CREATE INDEX idx_execution_workspace_scope ON execution_workspace_bindings(server_id,executor_id,workspace_id,status);

CREATE TABLE execution_bindings (
    server_id TEXT NOT NULL,
    binding_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    endpoint_id TEXT NOT NULL UNIQUE REFERENCES agent_endpoints(endpoint_id),
    workspace_binding_id TEXT NOT NULL,
    candidate_ref TEXT NOT NULL,
    inventory_revision TEXT NOT NULL,
    realization_ref TEXT NOT NULL,
    realization_revision INTEGER NOT NULL CHECK (realization_revision >= 1),
    binding_revision INTEGER NOT NULL CHECK (binding_revision >= 1),
    PRIMARY KEY (server_id, binding_id),
    UNIQUE (server_id, executor_id, binding_id),
    FOREIGN KEY (server_id, executor_id) REFERENCES execution_executors(server_id,executor_id),
    FOREIGN KEY (server_id, executor_id, workspace_binding_id) REFERENCES execution_workspace_bindings(server_id,executor_id,workspace_binding_id)
);
CREATE INDEX idx_execution_bindings_executor ON execution_bindings(server_id,executor_id,binding_id);

CREATE TABLE execution_realizations (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    realization_ref TEXT NOT NULL,
    local_realization_ref TEXT NOT NULL,
    subject_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    workspace_binding_id TEXT NOT NULL,
    candidate_ref TEXT NOT NULL,
    inventory_revision TEXT NOT NULL,
    configuration_digest TEXT NOT NULL,
    local_root_proof_digest TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    status TEXT NOT NULL,
    PRIMARY KEY (server_id,executor_id,realization_ref),
    UNIQUE (server_id,executor_id,local_realization_ref,revision),
    FOREIGN KEY (server_id,executor_id) REFERENCES execution_executors(server_id,executor_id),
    FOREIGN KEY (server_id,executor_id,workspace_binding_id) REFERENCES execution_workspace_bindings(server_id,executor_id,workspace_binding_id)
);
CREATE INDEX idx_execution_realizations_subject ON execution_realizations(server_id,subject_agent_id,executor_id,status);

CREATE TABLE execution_inventory_snapshots (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    publication_sequence INTEGER NOT NULL CHECK (publication_sequence >= 1),
    inventory_revision TEXT NOT NULL,
    catalog_format INTEGER NOT NULL CHECK (catalog_format >= 1),
    availability_format INTEGER NOT NULL CHECK (availability_format >= 1),
    snapshot_format INTEGER NOT NULL CHECK (snapshot_format >= 1),
    core_version TEXT NOT NULL,
    canonical_projection TEXT NOT NULL,
    received_at TEXT NOT NULL,
    observation_age_ms INTEGER NOT NULL CHECK (observation_age_ms >= 0),
    producer_instance_id TEXT NOT NULL,
    PRIMARY KEY (server_id,executor_id,publication_sequence),
    FOREIGN KEY (server_id,executor_id) REFERENCES execution_executors(server_id,executor_id)
);
CREATE INDEX idx_execution_inventory_revision ON execution_inventory_snapshots(server_id,executor_id,inventory_revision);

CREATE TABLE execution_inventory_current (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    publication_sequence INTEGER NOT NULL,
    inventory_revision TEXT NOT NULL,
    previous_revision TEXT,
    PRIMARY KEY (server_id,executor_id),
    FOREIGN KEY (server_id,executor_id,publication_sequence) REFERENCES execution_inventory_snapshots(server_id,executor_id,publication_sequence)
);

CREATE TABLE execution_proposals (
    proposal_id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    client_intent_id TEXT NOT NULL,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    subject_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    executor_id TEXT NOT NULL,
    binding_id TEXT,
    expected_revisions_json TEXT NOT NULL,
    diff_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (server_id,actor_agent_id,client_intent_id),
    FOREIGN KEY (server_id,executor_id) REFERENCES execution_executors(server_id,executor_id)
);
CREATE INDEX idx_execution_proposals_subject ON execution_proposals(server_id,subject_agent_id,status,expires_at);

CREATE TABLE execution_client_intents (
    server_id TEXT NOT NULL,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    client_intent_id TEXT NOT NULL,
    body_hash TEXT NOT NULL,
    intent_id TEXT NOT NULL,
    operation_id TEXT,
    resolution_revision INTEGER NOT NULL CHECK (resolution_revision >= 1),
    resolved_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (server_id,actor_agent_id,client_intent_id),
    UNIQUE (server_id,intent_id)
);

CREATE TABLE execution_operations (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    subject_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    binding_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    workspace_binding_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    action TEXT NOT NULL,
    intent_hash TEXT NOT NULL,
    semantic_payload TEXT NOT NULL,
    expected_revisions_json TEXT NOT NULL,
    decision_id TEXT,
    delivery_id TEXT,
    admission_state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (server_id,executor_id,operation_id),
    FOREIGN KEY (server_id,executor_id) REFERENCES execution_executors(server_id,executor_id),
    FOREIGN KEY (server_id,executor_id,binding_id) REFERENCES execution_bindings(server_id,executor_id,binding_id),
    FOREIGN KEY (server_id,executor_id,workspace_binding_id) REFERENCES execution_workspace_bindings(server_id,executor_id,workspace_binding_id)
);
CREATE INDEX idx_execution_operations_subject ON execution_operations(server_id,subject_agent_id,workspace_id,admission_state,created_at);
CREATE INDEX idx_execution_operations_session ON execution_operations(server_id,executor_id,session_id,created_at);

CREATE TABLE execution_dispatch_outbox (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    dispatch_state TEXT NOT NULL,
    attempt_token TEXT,
    attempt_no INTEGER NOT NULL DEFAULT 0 CHECK (attempt_no >= 0),
    connection_generation INTEGER,
    lease_id TEXT,
    lease_serial INTEGER,
    next_attempt_at TEXT,
    last_error TEXT,
    last_receipt_revision INTEGER,
    PRIMARY KEY (server_id,executor_id,operation_id),
    FOREIGN KEY (server_id,executor_id,operation_id) REFERENCES execution_operations(server_id,executor_id,operation_id)
);
CREATE INDEX idx_execution_dispatch_pending ON execution_dispatch_outbox(server_id,executor_id,dispatch_state,next_attempt_at);

CREATE TABLE execution_receipts (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    receipt_revision INTEGER NOT NULL CHECK (receipt_revision >= 1),
    intent_hash TEXT NOT NULL,
    stage TEXT NOT NULL,
    possible_effect INTEGER NOT NULL CHECK (possible_effect IN (0,1)),
    retry_safe INTEGER NOT NULL CHECK (retry_safe IN (0,1)),
    native_id TEXT,
    error_code TEXT,
    received_at TEXT NOT NULL,
    PRIMARY KEY (server_id,executor_id,operation_id,receipt_revision),
    FOREIGN KEY (server_id,executor_id,operation_id) REFERENCES execution_operations(server_id,executor_id,operation_id)
);

CREATE TABLE execution_sessions (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    binding_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    workspace_binding_id TEXT NOT NULL,
    open_operation_id TEXT NOT NULL,
    core_owner_ref TEXT,
    owner_generation INTEGER NOT NULL CHECK (owner_generation >= 1),
    lifecycle_state TEXT NOT NULL,
    ownership_proof_json TEXT,
    stream_epoch TEXT,
    lease_state TEXT NOT NULL,
    legacy_session_id TEXT,
    PRIMARY KEY (server_id,executor_id,session_id),
    UNIQUE (server_id,executor_id,open_operation_id),
    FOREIGN KEY (server_id,executor_id) REFERENCES execution_executors(server_id,executor_id),
    FOREIGN KEY (server_id,executor_id,binding_id) REFERENCES execution_bindings(server_id,executor_id,binding_id),
    FOREIGN KEY (server_id,executor_id,workspace_binding_id) REFERENCES execution_workspace_bindings(server_id,executor_id,workspace_binding_id)
);
CREATE INDEX idx_execution_sessions_binding ON execution_sessions(server_id,executor_id,binding_id,lifecycle_state);

CREATE TABLE execution_leases (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    lease_serial INTEGER NOT NULL CHECK (lease_serial >= 1),
    lease_id TEXT NOT NULL,
    grant_id TEXT NOT NULL,
    allowed_actions_json TEXT NOT NULL,
    authorization_revision INTEGER NOT NULL CHECK (authorization_revision >= 1),
    configuration_revision INTEGER NOT NULL CHECK (configuration_revision >= 1),
    owner_generation INTEGER NOT NULL CHECK (owner_generation >= 1),
    connection_generation INTEGER NOT NULL CHECK (connection_generation >= 1),
    credential_epoch INTEGER NOT NULL CHECK (credential_epoch >= 1),
    valid_until_server TEXT NOT NULL,
    request_id TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (server_id,executor_id,session_id,lease_serial),
    UNIQUE (server_id,executor_id,session_id,request_id),
    FOREIGN KEY (server_id,executor_id,session_id) REFERENCES execution_sessions(server_id,executor_id,session_id)
);
CREATE INDEX idx_execution_leases_expiration ON execution_leases(status,valid_until_server);

CREATE TABLE execution_link_tickets (
    ticket_id TEXT PRIMARY KEY,
    secret_hash TEXT NOT NULL UNIQUE,
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    binding_id TEXT,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    audience TEXT NOT NULL,
    scopes_json TEXT NOT NULL,
    credential_epoch INTEGER NOT NULL CHECK (credential_epoch >= 1),
    authorization_revision INTEGER NOT NULL CHECK (authorization_revision >= 1),
    expires_at TEXT NOT NULL,
    bound_connection_id TEXT,
    revoked_at TEXT,
    FOREIGN KEY (server_id,executor_id) REFERENCES execution_executors(server_id,executor_id),
    FOREIGN KEY (server_id,executor_id,binding_id) REFERENCES execution_bindings(server_id,executor_id,binding_id)
);
CREATE INDEX idx_execution_tickets_scope ON execution_link_tickets(server_id,executor_id,binding_id,agent_id,expires_at);

CREATE TABLE execution_session_capabilities (
    capability_id TEXT PRIMARY KEY,
    secret_hash TEXT NOT NULL UNIQUE,
    audience TEXT NOT NULL,
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    subject_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    actions_json TEXT NOT NULL,
    valid_until_server TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (server_id,executor_id,session_id) REFERENCES execution_sessions(server_id,executor_id,session_id)
);
CREATE INDEX idx_execution_capabilities_session ON execution_session_capabilities(server_id,executor_id,session_id,audience);

CREATE TABLE execution_event_ingress (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    stream_epoch TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    event_hash TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    received_at TEXT NOT NULL,
    PRIMARY KEY (server_id,executor_id,session_id,stream_epoch,sequence),
    FOREIGN KEY (server_id,executor_id,session_id) REFERENCES execution_sessions(server_id,executor_id,session_id)
);

CREATE TABLE execution_event_watermarks (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    stream_epoch TEXT NOT NULL,
    committed_contiguous INTEGER NOT NULL DEFAULT 0 CHECK (committed_contiguous >= 0),
    projected_through INTEGER NOT NULL DEFAULT 0 CHECK (projected_through >= 0),
    gap_state TEXT NOT NULL DEFAULT 'none',
    PRIMARY KEY (server_id,executor_id,session_id,stream_epoch),
    FOREIGN KEY (server_id,executor_id,session_id) REFERENCES execution_sessions(server_id,executor_id,session_id)
);

CREATE TABLE execution_decisions (
    decision_id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    binding_id TEXT NOT NULL,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
    session_id TEXT NOT NULL,
    session_owner_generation INTEGER NOT NULL CHECK (session_owner_generation >= 1),
    canonical_request_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    proposal_json TEXT NOT NULL,
    proposal_digest TEXT NOT NULL,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    decision TEXT,
    canonical_state TEXT NOT NULL,
    native_operation_id TEXT,
    response_digest TEXT,
    response_ref TEXT,
    expires_at TEXT NOT NULL,
    UNIQUE (server_id,executor_id,binding_id,agent_id,workspace_id,session_id,session_owner_generation,canonical_request_id,kind,revision),
    FOREIGN KEY (server_id,executor_id,session_id) REFERENCES execution_sessions(server_id,executor_id,session_id)
);
CREATE INDEX idx_execution_decisions_pending ON execution_decisions(server_id,agent_id,canonical_state,expires_at);

CREATE TABLE execution_migration_map (
    source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    legacy_id TEXT NOT NULL,
    canonical_ref TEXT NOT NULL,
    row_digest_before TEXT NOT NULL,
    migration_batch_id TEXT NOT NULL,
    state TEXT NOT NULL,
    PRIMARY KEY (source,source_type,legacy_id)
);
