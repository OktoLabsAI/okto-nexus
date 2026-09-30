-- Private local mapping; public realization projections contain no paths or material.
CREATE TABLE execution_local_realizations (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    realization_ref TEXT NOT NULL,
    actor_agent_id TEXT NOT NULL,
    subject_agent_id TEXT NOT NULL,
    client_intent_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    local_record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (server_id, executor_id, realization_ref),
    UNIQUE (server_id, executor_id, subject_agent_id, client_intent_id),
    FOREIGN KEY (server_id, executor_id, realization_ref)
        REFERENCES execution_realizations(server_id, executor_id, realization_ref)
);
