CREATE TABLE runtime_policy_defaults (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    runtime_enabled INTEGER NOT NULL CHECK(runtime_enabled IN (0,1)),
    session_policy TEXT NOT NULL CHECK(session_policy IN ('shared','per_sender')),
    revision INTEGER NOT NULL CHECK(revision>0)
);
INSERT INTO runtime_policy_defaults VALUES(1,1,'shared',1);

CREATE TABLE agent_runtime_policy_epochs (
    agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id),
    epoch INTEGER NOT NULL CHECK(epoch>0)
);

CREATE TABLE agent_runtime_overrides (
    agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id),
    runtime_enabled INTEGER CHECK(runtime_enabled IN (0,1)),
    session_policy TEXT CHECK(session_policy IN ('shared','per_sender')),
    revision INTEGER NOT NULL CHECK(revision>0)
);
-- Preserve the explicit isolation selected before global defaults existed.
INSERT INTO agent_runtime_overrides(agent_id,runtime_enabled,session_policy,revision)
SELECT DISTINCT agent_id,NULL,'per_sender',1 FROM agent_endpoints WHERE session_policy='per_sender';

-- Refuse execution writers that do not enforce global and per-agent defaults.

CREATE TRIGGER runtime_defaults_execution_operations_insert
BEFORE INSERT ON execution_operations
WHEN EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_execution_operations_update
BEFORE UPDATE ON execution_operations
WHEN EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_execution_operations_delete
BEFORE DELETE ON execution_operations
WHEN EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_execution_dispatch_outbox_insert
BEFORE INSERT ON execution_dispatch_outbox
WHEN EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_execution_dispatch_outbox_update
BEFORE UPDATE ON execution_dispatch_outbox
WHEN EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_execution_dispatch_outbox_delete
BEFORE DELETE ON execution_dispatch_outbox
WHEN EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_execution_leases_insert
BEFORE INSERT ON execution_leases
WHEN EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_execution_leases_update
BEFORE UPDATE ON execution_leases
WHEN EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_execution_leases_delete
BEFORE DELETE ON execution_leases
WHEN EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
AND NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_agent_runtime_overrides_insert
BEFORE INSERT ON agent_runtime_overrides
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_agent_runtime_overrides_update
BEFORE UPDATE ON agent_runtime_overrides
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_agent_runtime_overrides_delete
BEFORE DELETE ON agent_runtime_overrides
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_runtime_policy_defaults_insert
BEFORE INSERT ON runtime_policy_defaults
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_runtime_policy_defaults_update
BEFORE UPDATE ON runtime_policy_defaults
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;

CREATE TRIGGER runtime_defaults_runtime_policy_defaults_delete
BEFORE DELETE ON runtime_policy_defaults
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_runtime_policy_defaults_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_policy_defaults_writer_incompatible');
END;
