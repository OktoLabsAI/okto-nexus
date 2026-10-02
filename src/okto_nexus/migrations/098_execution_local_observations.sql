CREATE TABLE execution_local_observations (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    candidate_ref TEXT NOT NULL,
    core_version TEXT NOT NULL,
    platform TEXT NOT NULL,
    source_json TEXT NOT NULL,
    version TEXT NOT NULL,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    observed_at TEXT NOT NULL,
    PRIMARY KEY(server_id,executor_id,candidate_ref),
    FOREIGN KEY(server_id,executor_id) REFERENCES execution_executors(server_id,executor_id)
);
