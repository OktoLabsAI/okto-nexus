CREATE TABLE agent_execution_policies (
    agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id),
    execution_location TEXT NOT NULL DEFAULT 'all' CHECK (execution_location IN ('local','remote','all')),
    local_adapter_id TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0)
);

-- A process opened before this migration cannot ignore the new execution policy
-- or reactivate retired connections. Reads and offline backups remain available.

CREATE TRIGGER agent_execution_policy_execution_operations_insert
BEFORE INSERT ON execution_operations
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_execution_operations_update
BEFORE UPDATE ON execution_operations
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_execution_operations_delete
BEFORE DELETE ON execution_operations
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_execution_dispatch_outbox_insert
BEFORE INSERT ON execution_dispatch_outbox
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_execution_dispatch_outbox_update
BEFORE UPDATE ON execution_dispatch_outbox
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_execution_dispatch_outbox_delete
BEFORE DELETE ON execution_dispatch_outbox
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_execution_leases_insert
BEFORE INSERT ON execution_leases
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_execution_leases_update
BEFORE UPDATE ON execution_leases
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_execution_leases_delete
BEFORE DELETE ON execution_leases
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_agent_execution_policies_insert
BEFORE INSERT ON agent_execution_policies
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_agent_execution_policies_update
BEFORE UPDATE ON agent_execution_policies
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_agent_execution_policies_delete
BEFORE DELETE ON agent_execution_policies
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_runtime_open_requests_insert
BEFORE INSERT ON runtime_open_requests
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_runtime_open_requests_update
BEFORE UPDATE ON runtime_open_requests
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_runtime_open_requests_delete
BEFORE DELETE ON runtime_open_requests
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_harness_sessions_insert
BEFORE INSERT ON harness_sessions
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_harness_sessions_update
BEFORE UPDATE ON harness_sessions
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;

CREATE TRIGGER agent_execution_policy_harness_sessions_delete
BEFORE DELETE ON harness_sessions
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible');
END;
