ALTER TABLE runtime_handoff_bindings ADD COLUMN completion_mode TEXT NOT NULL DEFAULT 'authenticated_nexus_call'
    CHECK(completion_mode IN ('authenticated_nexus_call','structured_result_v1'));
CREATE INDEX idx_runtime_work_completion ON runtime_handoff_bindings(completion_mode,operation_id);
CREATE TABLE runtime_work_outcomes (
    result_id TEXT PRIMARY KEY REFERENCES runtime_results(result_id) ON DELETE RESTRICT,
    operation_id TEXT NOT NULL UNIQUE REFERENCES delivery_outbox(operation_id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK(state IN ('APPLIED','IGNORED','BLOCKED')),
    response TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);
