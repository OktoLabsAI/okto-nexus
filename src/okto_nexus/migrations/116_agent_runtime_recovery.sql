-- Recovery of a known local subject does not revoke the shared host.
CREATE TABLE execution_agent_recovery (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    generation INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('RECOVERING','READY')),
    attempts INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(server_id,executor_id,agent_id),
    FOREIGN KEY(server_id,executor_id) REFERENCES execution_executors(server_id,executor_id)
);
ALTER TABLE runtime_recovery_events ADD COLUMN agent_id TEXT REFERENCES agents(agent_id);
ALTER TABLE execution_local_streams ADD COLUMN drained INTEGER NOT NULL DEFAULT 0 CHECK(drained IN (0,1));
ALTER TABLE runtime_dispatcher_owner ADD COLUMN process_pid INTEGER;
ALTER TABLE runtime_dispatcher_owner ADD COLUMN process_host TEXT;
-- These messages never crossed the execution boundary. Resume automatic checks;
-- permission/configuration failures remain in attention for explicit correction.
UPDATE runtime_pending_deliveries SET status='waiting'
WHERE status='attention' AND reason IN (
    'Automatic runtime recovery attempts exhausted',
    'Recovery wait limit reached; message was not submitted'
);
