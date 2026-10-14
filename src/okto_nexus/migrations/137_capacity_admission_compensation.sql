-- Retain exact operations and host proof when a committed claim never consumed
-- its ticket. A terminal attempt must no longer exclude fresh candidacy.
CREATE TABLE execution_capacity_admissions_new (
    domain_operation_id TEXT PRIMARY KEY REFERENCES delivery_outbox(operation_id),
    attempt_id TEXT NOT NULL UNIQUE,
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    reservation_json TEXT NOT NULL,
    consumption_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('WAITING_CONSUMPTION','CONSUMED','NEEDS_RECONCILIATION','CANCELLED_NO_EFFECT')),
    reason TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(server_id,executor_id,session_id) REFERENCES execution_sessions(server_id,executor_id,session_id)
);
INSERT INTO execution_capacity_admissions_new SELECT * FROM execution_capacity_admissions;
DROP TABLE execution_capacity_admissions;
ALTER TABLE execution_capacity_admissions_new RENAME TO execution_capacity_admissions;
CREATE INDEX execution_capacity_admissions_session ON execution_capacity_admissions(server_id,executor_id,session_id);
CREATE INDEX execution_capacity_admissions_pending ON execution_capacity_admissions(state,updated_at,domain_operation_id);

CREATE TABLE handoff_runtime_attempts_new (
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
    CHECK(operation_id IS NULL OR (state='CLAIM_COMMITTED' AND active=1 AND disposition='ACQUIRE')
        OR (state='CANCELLED_NO_EFFECT' AND active=0 AND disposition='RELEASE')),
    CHECK(active=1 OR (state='NOT_AVAILABLE' AND operation_id IS NULL) OR state='CANCELLED_NO_EFFECT')
);
INSERT INTO handoff_runtime_attempts_new SELECT * FROM handoff_runtime_attempts;
DROP TABLE handoff_runtime_attempts;
ALTER TABLE handoff_runtime_attempts_new RENAME TO handoff_runtime_attempts;
CREATE UNIQUE INDEX handoff_runtime_attempts_candidate
    ON handoff_runtime_attempts(workspace_id,handoff_id,agent_id) WHERE active=1;
CREATE INDEX handoff_runtime_attempts_pending ON handoff_runtime_attempts(active,updated_at,attempt_id);

CREATE TABLE execution_capacity_compensations (
    domain_operation_id TEXT PRIMARY KEY REFERENCES execution_capacity_admissions(domain_operation_id),
    reservation_json TEXT NOT NULL,
    actor_kind TEXT NOT NULL CHECK(actor_kind='system'),
    reason TEXT NOT NULL CHECK(reason IN ('EXPIRED_UNCONSUMED','RELEASED')),
    recorded_at TEXT NOT NULL
);
