-- Calls and capacity reservations survive process/server restarts. A terminal
-- result does not release capacity: the host must confirm resource disposal.
CREATE TABLE one_shot_calls (
    call_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    executor_id TEXT NOT NULL,
    caller_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    configuration_digest TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('QUEUED','ADMITTED','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
    enqueued_at REAL NOT NULL,
    queue_deadline REAL NOT NULL,
    started_at REAL,
    execution_deadline REAL,
    admission_deadline REAL,
    outcome_json TEXT,
    outcome_delivered_at REAL,
    outcome_attempts INTEGER NOT NULL DEFAULT 0 CHECK(outcome_attempts>=0)
);
CREATE INDEX one_shot_fifo ON one_shot_calls(executor_id,agent_id,state,enqueued_at,call_id);
CREATE TABLE one_shot_slots (
    slot_id TEXT PRIMARY KEY,
    executor_id TEXT NOT NULL,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    configuration_digest TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('STARTING','WARM','CLAIMED','RUNNING','CLOSING')),
    call_id TEXT UNIQUE REFERENCES one_shot_calls(call_id),
    created_at REAL NOT NULL,
    session_id TEXT,
    close_attempts INTEGER NOT NULL DEFAULT 0 CHECK(close_attempts>=0)
);
CREATE INDEX one_shot_host_capacity ON one_shot_slots(executor_id,agent_id,state);
CREATE TABLE one_shot_warm_backoff (
    executor_id TEXT NOT NULL,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    failures INTEGER NOT NULL DEFAULT 0 CHECK(failures>=0),
    next_attempt_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY(executor_id,agent_id)
);
CREATE TABLE one_shot_policy_settings (
    scope TEXT PRIMARY KEY,
    revision INTEGER NOT NULL CHECK(revision>0),
    policy_json TEXT NOT NULL
);
INSERT INTO one_shot_policy_settings VALUES ('global',1,
    '{"max_parallel":1,"warm_instances":0,"overflow":"queue","queue_capacity":32,"queue_timeout_seconds":300,"execution_timeout_seconds":1800}');
CREATE TABLE runtime_mcp_presets (
    endpoint_id TEXT PRIMARY KEY REFERENCES agent_endpoints(endpoint_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL CHECK(revision>0),
    preset_json TEXT NOT NULL,
    configuration_digest TEXT NOT NULL
);
