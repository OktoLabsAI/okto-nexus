-- Security causality is independent of optional telemetry/traces.
CREATE TABLE runtime_causal_roots (
    root_operation_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    deadline TEXT NOT NULL,
    max_depth INTEGER NOT NULL CHECK(max_depth>=0),
    max_messages INTEGER NOT NULL CHECK(max_messages>0),
    max_executions INTEGER NOT NULL CHECK(max_executions>0),
    generated_messages INTEGER NOT NULL DEFAULT 0 CHECK(generated_messages>=0),
    admitted_executions INTEGER NOT NULL DEFAULT 0 CHECK(admitted_executions>=0)
);
CREATE INDEX runtime_causal_root_actor ON runtime_causal_roots(actor_agent_id,created_at);
CREATE INDEX runtime_causal_root_workspace ON runtime_causal_roots(workspace_id,created_at);
CREATE TABLE runtime_message_causality (
    message_id TEXT PRIMARY KEY REFERENCES messages(message_id) ON DELETE RESTRICT,
    root_operation_id TEXT NOT NULL REFERENCES runtime_causal_roots(root_operation_id) ON DELETE RESTRICT,
    parent_message_id TEXT REFERENCES messages(message_id) ON DELETE RESTRICT,
    hop_count INTEGER NOT NULL CHECK(hop_count>=0),
    purpose TEXT NOT NULL CHECK(purpose IN ('entry','continuation','observation')),
    source_result_id TEXT UNIQUE REFERENCES runtime_results(result_id) ON DELETE RESTRICT
);
CREATE INDEX runtime_message_causal_root ON runtime_message_causality(root_operation_id);
CREATE INDEX runtime_message_causal_parent ON runtime_message_causality(parent_message_id);
CREATE INDEX runtime_result_publication_message ON runtime_results(publication_message_id);
