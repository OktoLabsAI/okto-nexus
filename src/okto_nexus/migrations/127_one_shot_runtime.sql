ALTER TABLE agent_endpoints ADD COLUMN session_policy_next TEXT NOT NULL DEFAULT 'shared'
    CHECK(session_policy_next IN ('shared','per_sender','per_sender_session','one_shot'));
UPDATE agent_endpoints SET session_policy_next=session_policy;
ALTER TABLE agent_endpoints DROP COLUMN session_policy;
ALTER TABLE agent_endpoints RENAME COLUMN session_policy_next TO session_policy;
ALTER TABLE runtime_policy_defaults ADD COLUMN session_policy_next TEXT NOT NULL DEFAULT 'shared'
    CHECK(session_policy_next IN ('shared','per_sender','per_sender_session','one_shot'));
UPDATE runtime_policy_defaults SET session_policy_next=session_policy;
ALTER TABLE runtime_policy_defaults DROP COLUMN session_policy;
ALTER TABLE runtime_policy_defaults RENAME COLUMN session_policy_next TO session_policy;
ALTER TABLE agent_runtime_overrides ADD COLUMN session_policy_next TEXT
    CHECK(session_policy_next IN ('shared','per_sender','per_sender_session','one_shot'));
UPDATE agent_runtime_overrides SET session_policy_next=session_policy;
ALTER TABLE agent_runtime_overrides DROP COLUMN session_policy;
ALTER TABLE agent_runtime_overrides RENAME COLUMN session_policy_next TO session_policy;
ALTER TABLE one_shot_slots ADD COLUMN server_id TEXT;
ALTER TABLE one_shot_slots ADD COLUMN binding_id TEXT;
ALTER TABLE one_shot_slots ADD COLUMN open_operation_id TEXT;
ALTER TABLE one_shot_slots ADD COLUMN close_operation_id TEXT;
ALTER TABLE one_shot_slots ADD COLUMN next_cleanup_at REAL NOT NULL DEFAULT 0;
ALTER TABLE one_shot_slots ADD COLUMN last_checked_at REAL NOT NULL DEFAULT 0;
CREATE TABLE one_shot_host_limits (
    executor_id TEXT PRIMARY KEY,
    max_instances INTEGER NOT NULL CHECK(max_instances BETWEEN 1 AND 1024)
);
ALTER TABLE one_shot_calls ADD COLUMN notification_message_id TEXT;
