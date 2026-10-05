-- Administrative controls are transport intents, not another handoff authority.
CREATE TABLE runtime_commands (
    operation_id TEXT PRIMARY KEY,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    context TEXT NOT NULL,
    grant_id TEXT REFERENCES runtime_execution_grants(grant_id) ON DELETE RESTRICT,
    grant_revision INTEGER,
    runtime_session_id TEXT NOT NULL REFERENCES harness_sessions(session_id) ON DELETE RESTRICT,
    endpoint_id TEXT NOT NULL REFERENCES agent_endpoints(endpoint_id) ON DELETE RESTRICT,
    endpoint_revision INTEGER NOT NULL,
    profile_revision INTEGER,
    verb TEXT NOT NULL CHECK(verb IN ('send_turn','steer','interrupt','close')),
    payload TEXT NOT NULL,
    starts_turn INTEGER NOT NULL CHECK(starts_turn IN (0,1)),
    expected_owner_epoch INTEGER NOT NULL,
    expected_operation_id TEXT,
    expected_turn_id TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','CLAIMED','SENDING','SENT_UNCONFIRMED','ACCEPTED','OUTCOME_UNKNOWN','REJECTED','CANCELLED','DONE')),
    owner_epoch INTEGER,
    attempt_id TEXT,
    ack_level TEXT NOT NULL DEFAULT 'NONE',
    native_thread_id TEXT,
    native_turn_id TEXT,
    terminal_event_id TEXT REFERENCES harness_events(event_id) ON DELETE RESTRICT,
    reason TEXT,
    result TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(actor_agent_id,idempotency_key)
);
CREATE INDEX idx_runtime_command_pending ON runtime_commands(status,verb,created_at,operation_id);
CREATE INDEX idx_runtime_command_lane ON runtime_commands(endpoint_id,status,verb);
ALTER TABLE runtime_results ADD COLUMN command_operation_id TEXT REFERENCES runtime_commands(operation_id) ON DELETE RESTRICT;
