-- Execution location is exclusive; existing All selections become Local.
CREATE TABLE agent_execution_policies_exclusive (
    agent_id TEXT PRIMARY KEY REFERENCES agents(agent_id),
    execution_location TEXT NOT NULL DEFAULT 'local' CHECK (execution_location IN ('local','remote')),
    local_adapter_id TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0)
);
INSERT INTO agent_execution_policies_exclusive
SELECT agent_id, CASE WHEN execution_location='all' THEN 'local' ELSE execution_location END,
       local_adapter_id, revision + CASE WHEN execution_location='all' THEN 1 ELSE 0 END
FROM agent_execution_policies;
DROP TABLE agent_execution_policies;
ALTER TABLE agent_execution_policies_exclusive RENAME TO agent_execution_policies;
CREATE TRIGGER agent_execution_policy_agent_execution_policies_insert
BEFORE INSERT ON agent_execution_policies
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible'); END;
CREATE TRIGGER agent_execution_policy_agent_execution_policies_update
BEFORE UPDATE ON agent_execution_policies
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible'); END;
CREATE TRIGGER agent_execution_policy_agent_execution_policies_delete
BEFORE DELETE ON agent_execution_policies
WHEN NOT EXISTS(SELECT 1 FROM pragma_function_list WHERE name='nexus_agent_execution_policy_v1' AND builtin=0 AND narg=0)
BEGIN SELECT RAISE(ABORT, 'agent_execution_policy_writer_incompatible'); END;
