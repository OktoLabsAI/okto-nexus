-- Connection policy is separate from the canonical agent skill/profile data.
CREATE TABLE agent_connection_policies (
    agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id) ON DELETE CASCADE,
    key_ttl_seconds INTEGER CHECK(key_ttl_seconds >= 0),
    revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE agent_connection_methods (
    agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    method TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    PRIMARY KEY(agent_id,method)
);
CREATE TABLE agent_connection_keys (
    key_id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    endpoint_id TEXT NOT NULL REFERENCES agent_endpoints(endpoint_id),
    endpoint_revision INTEGER NOT NULL,
    profile_revision INTEGER,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    revoked_at TEXT,
    source_grant_id TEXT REFERENCES runtime_execution_grants(grant_id)
);
CREATE INDEX agent_connection_keys_agent ON agent_connection_keys(agent_id,created_at);
ALTER TABLE runtime_open_requests ADD COLUMN connection_key_id TEXT REFERENCES agent_connection_keys(key_id);

CREATE TRIGGER connection_policy_runtime_open_requests_insert
BEFORE INSERT ON runtime_open_requests
WHEN (EXISTS(SELECT 1 FROM agent_connection_methods) OR EXISTS(SELECT 1 FROM agent_connection_keys))
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_connection_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER connection_policy_runtime_open_requests_update
BEFORE UPDATE ON runtime_open_requests
WHEN (EXISTS(SELECT 1 FROM agent_connection_methods) OR EXISTS(SELECT 1 FROM agent_connection_keys))
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_connection_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER connection_policy_runtime_open_requests_delete
BEFORE DELETE ON runtime_open_requests
WHEN (EXISTS(SELECT 1 FROM agent_connection_methods) OR EXISTS(SELECT 1 FROM agent_connection_keys))
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_connection_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER connection_policy_harness_sessions_insert
BEFORE INSERT ON harness_sessions
WHEN (EXISTS(SELECT 1 FROM agent_connection_methods) OR EXISTS(SELECT 1 FROM agent_connection_keys))
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_connection_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER connection_policy_harness_sessions_update
BEFORE UPDATE ON harness_sessions
WHEN (EXISTS(SELECT 1 FROM agent_connection_methods) OR EXISTS(SELECT 1 FROM agent_connection_keys))
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_connection_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER connection_policy_harness_sessions_delete
BEFORE DELETE ON harness_sessions
WHEN (EXISTS(SELECT 1 FROM agent_connection_methods) OR EXISTS(SELECT 1 FROM agent_connection_keys))
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_connection_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER connection_policy_delivery_outbox_insert
BEFORE INSERT ON delivery_outbox
WHEN (EXISTS(SELECT 1 FROM agent_connection_methods) OR EXISTS(SELECT 1 FROM agent_connection_keys))
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_connection_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER connection_policy_delivery_outbox_update
BEFORE UPDATE ON delivery_outbox
WHEN (EXISTS(SELECT 1 FROM agent_connection_methods) OR EXISTS(SELECT 1 FROM agent_connection_keys))
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_connection_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER connection_policy_delivery_outbox_delete
BEFORE DELETE ON delivery_outbox
WHEN (EXISTS(SELECT 1 FROM agent_connection_methods) OR EXISTS(SELECT 1 FROM agent_connection_keys))
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_connection_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER connection_policy_runtime_commands_insert
BEFORE INSERT ON runtime_commands
WHEN (EXISTS(SELECT 1 FROM agent_connection_methods) OR EXISTS(SELECT 1 FROM agent_connection_keys))
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_connection_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER connection_policy_runtime_commands_update
BEFORE UPDATE ON runtime_commands
WHEN (EXISTS(SELECT 1 FROM agent_connection_methods) OR EXISTS(SELECT 1 FROM agent_connection_keys))
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_connection_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER connection_policy_runtime_commands_delete
BEFORE DELETE ON runtime_commands
WHEN (EXISTS(SELECT 1 FROM agent_connection_methods) OR EXISTS(SELECT 1 FROM agent_connection_keys))
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_connection_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;
