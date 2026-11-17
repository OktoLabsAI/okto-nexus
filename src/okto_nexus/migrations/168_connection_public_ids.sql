-- Public product metadata only. No execution authority or runtime state.
CREATE TABLE connection_project_drafts (
    server_id TEXT NOT NULL,
    project_draft_ref TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    directory_key TEXT NOT NULL,
    project_revision TEXT NOT NULL,
    workspace_label TEXT NOT NULL,
    actor_agent_id TEXT NOT NULL,
    client_intent_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('reserved','bound','retired')),
    workspace_id TEXT,
    revision INTEGER NOT NULL CHECK(revision >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(server_id,project_draft_ref),
    UNIQUE(server_id,actor_agent_id,client_intent_id)
);
CREATE UNIQUE INDEX connection_project_draft_pending_root
    ON connection_project_drafts(server_id,executor_id,directory_key) WHERE state='reserved';

CREATE TABLE connection_public_ids (
    server_id TEXT NOT NULL,
    reservation_ref TEXT NOT NULL,
    actor_agent_id TEXT NOT NULL,
    client_intent_id TEXT NOT NULL,
    namespace_ref TEXT NOT NULL,
    workspace_id TEXT,
    project_draft_ref TEXT,
    connect_id TEXT NOT NULL CHECK(length(connect_id) BETWEEN 1 AND 64
        AND substr(connect_id,1,1) GLOB '[a-z]' AND connect_id NOT GLOB '*[^a-z0-9_-]*'),
    state TEXT NOT NULL CHECK(state IN ('reserved','bound','retired')),
    request_hash TEXT NOT NULL,
    adapter_id TEXT,
    canonical_ref_json TEXT,
    revision INTEGER NOT NULL CHECK(revision >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(server_id,reservation_ref),
    UNIQUE(server_id,namespace_ref,connect_id),
    UNIQUE(server_id,actor_agent_id,client_intent_id),
    FOREIGN KEY(server_id,project_draft_ref) REFERENCES connection_project_drafts(server_id,project_draft_ref),
    CHECK(state <> 'bound' OR (workspace_id IS NOT NULL AND canonical_ref_json IS NOT NULL))
);
-- Historical IDs survive binding/workspace retirement instead of redirecting
-- old commands to a successor. References are validated at every mutation.
CREATE UNIQUE INDEX connection_public_id_workspace
    ON connection_public_ids(server_id,workspace_id,connect_id) WHERE workspace_id IS NOT NULL;
CREATE UNIQUE INDEX connection_public_id_binding
    ON connection_public_ids(server_id,json_extract(canonical_ref_json,'$.executor_id'),
        json_extract(canonical_ref_json,'$.binding_id')) WHERE canonical_ref_json IS NOT NULL;
