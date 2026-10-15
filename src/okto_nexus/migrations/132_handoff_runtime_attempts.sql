-- This is an attempt journal, not a second source of handoff ownership.
CREATE TABLE handoff_runtime_attempts (
    attempt_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    handoff_id TEXT NOT NULL REFERENCES handoffs(handoff_id),
    agent_id TEXT NOT NULL,
    claim_generation INTEGER NOT NULL CHECK(claim_generation >= 0),
    principal_json TEXT NOT NULL,
    request_json TEXT NOT NULL,
    reservation_json TEXT,
    operation_id TEXT UNIQUE REFERENCES delivery_outbox(operation_id),
    state TEXT NOT NULL CHECK(state IN ('WAITING','RESERVING','RESERVED','NOT_AVAILABLE',
        'RELEASE_PENDING','NEEDS_RECONCILIATION','CLAIM_COMMITTED','CANCELLED_NO_EFFECT')),
    disposition TEXT NOT NULL CHECK(disposition IN ('ACQUIRE','RELEASE')),
    reserve_started INTEGER NOT NULL DEFAULT 0 CHECK(reserve_started IN (0,1)),
    active INTEGER NOT NULL CHECK(active IN (0,1)),
    reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK(operation_id IS NULL OR (state='CLAIM_COMMITTED' AND active=1 AND disposition='ACQUIRE')),
    CHECK(active=1 OR (state IN ('NOT_AVAILABLE','CANCELLED_NO_EFFECT') AND operation_id IS NULL))
);
-- A new binding, generation or another scheduler worker cannot multiply this
-- agent's candidacy while its preceding reservation/effects remain unresolved.
CREATE UNIQUE INDEX handoff_runtime_attempts_candidate
    ON handoff_runtime_attempts(workspace_id,handoff_id,agent_id) WHERE active=1;
CREATE INDEX handoff_runtime_attempts_pending
    ON handoff_runtime_attempts(active,updated_at,attempt_id);
