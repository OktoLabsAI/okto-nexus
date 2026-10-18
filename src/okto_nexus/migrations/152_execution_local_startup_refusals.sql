-- A pre-authorization failure belongs to one opening, not its entire agent.
-- Persist the exact Core refusal association before fencing the opening.
CREATE TABLE execution_local_startup_refusals (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    refusal_json TEXT NOT NULL,
    report_json TEXT,
    accepted_at TEXT,
    PRIMARY KEY (server_id, executor_id, operation_id)
);

CREATE INDEX idx_execution_local_startup_refusals_pending
ON execution_local_startup_refusals (server_id, executor_id, agent_id, accepted_at, operation_id);
