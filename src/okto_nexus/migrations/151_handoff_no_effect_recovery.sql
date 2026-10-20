-- foreign-key-rebuild
-- Preserve the consumed admission and failed operation while retiring its
-- candidate. Only a proved no-effect, physically released opening can enter
-- FAILED_NO_EFFECT. A retry gets a fresh attempt and claim epoch.
CREATE TABLE handoff_runtime_attempts_rebuilt (
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
        'RELEASE_PENDING','NEEDS_RECONCILIATION','CLAIM_COMMITTED','CANCELLED_NO_EFFECT','FAILED_NO_EFFECT')),
    disposition TEXT NOT NULL CHECK(disposition IN ('ACQUIRE','RELEASE')),
    reserve_started INTEGER NOT NULL DEFAULT 0 CHECK(reserve_started IN (0,1)),
    active INTEGER NOT NULL CHECK(active IN (0,1)),
    reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK(operation_id IS NULL OR (state='CLAIM_COMMITTED' AND active=1 AND disposition='ACQUIRE')
        OR (state='FAILED_NO_EFFECT' AND active=0 AND disposition='RELEASE')),
    CHECK(active=1 OR (state IN ('NOT_AVAILABLE','CANCELLED_NO_EFFECT') AND operation_id IS NULL)
        OR (state='FAILED_NO_EFFECT' AND operation_id IS NOT NULL))
);
INSERT INTO handoff_runtime_attempts_rebuilt SELECT * FROM handoff_runtime_attempts;
DROP TABLE handoff_runtime_attempts;
ALTER TABLE handoff_runtime_attempts_rebuilt RENAME TO handoff_runtime_attempts;
CREATE UNIQUE INDEX handoff_runtime_attempts_candidate
    ON handoff_runtime_attempts(workspace_id,handoff_id,agent_id) WHERE active=1;
CREATE INDEX handoff_runtime_attempts_pending
    ON handoff_runtime_attempts(active,updated_at,attempt_id);
CREATE INDEX handoff_runtime_attempts_agent_history
    ON handoff_runtime_attempts(agent_id,updated_at DESC,attempt_id DESC);
CREATE INDEX handoff_runtime_attempts_recent
    ON handoff_runtime_attempts(updated_at DESC,attempt_id DESC);

CREATE TABLE handoff_runtime_no_effect_retries (
    handoff_id TEXT NOT NULL REFERENCES handoffs(handoff_id),
    agent_id TEXT NOT NULL,
    failure_count INTEGER NOT NULL CHECK(failure_count >= 1),
    retry_after REAL NOT NULL,
    last_operation_id TEXT NOT NULL UNIQUE REFERENCES delivery_outbox(operation_id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(handoff_id,agent_id)
);
CREATE INDEX handoff_runtime_no_effect_retry_due ON handoff_runtime_no_effect_retries(retry_after,handoff_id);

-- The view is an index-backed candidate set for the bounded scheduler sweep.
-- The application re-reads it inside the same writer transaction as reopening.
CREATE VIEW handoff_runtime_proved_no_effect AS
SELECT h.handoff_id,h.workspace_id,h.claim_epoch,b.operation_id,a.attempt_id,
       a.agent_id,s.session_id,r.error_code
FROM handoffs h
JOIN runtime_handoff_bindings b ON b.handoff_id=h.handoff_id AND b.claim_epoch=h.claim_epoch
JOIN delivery_outbox o ON o.operation_id=b.operation_id
JOIN handoff_runtime_attempts a ON a.operation_id=b.operation_id
JOIN one_shot_calls c ON c.call_id=b.operation_id
JOIN execution_capacity_admissions cap ON cap.domain_operation_id=b.operation_id
JOIN execution_sessions s ON s.server_id=cap.server_id AND s.executor_id=cap.executor_id
    AND s.session_id=cap.session_id
JOIN execution_domain_deliveries od ON od.domain_operation_id=b.operation_id
JOIN execution_operations opening ON opening.server_id=od.server_id AND opening.executor_id=od.executor_id
    AND opening.operation_id=od.operation_id AND opening.action='runtime.open'
JOIN execution_receipts r ON r.server_id=opening.server_id AND r.executor_id=opening.executor_id
    AND r.operation_id=opening.operation_id
JOIN execution_domain_deliveries td ON td.domain_operation_id=b.operation_id
JOIN execution_operations turn ON turn.server_id=td.server_id AND turn.executor_id=td.executor_id
    AND turn.operation_id=td.operation_id AND turn.action='turn.submit'
JOIN execution_dispatch_outbox tx ON tx.server_id=turn.server_id AND tx.executor_id=turn.executor_id
    AND tx.operation_id=turn.operation_id
WHERE h.status='CLAIMED' AND h.claimed_by=a.agent_id AND a.active=1
  AND a.state='CLAIM_COMMITTED' AND cap.state='CONSUMED'
  AND o.status='FAILED_FINAL' AND o.reconciliation_id IS NULL AND o.external_completed_at IS NULL
  AND c.state='FAILED' AND json_extract(c.outcome_json,'$.error.execution_started')=0
  AND json_extract(c.outcome_json,'$.error.possible_effect')=0
  AND json_extract(c.outcome_json,'$.error.retry_safe')=1
  AND s.lifecycle_state='CLOSED' AND s.lease_state='CLOSED'
  AND r.stage='FAILED' AND r.possible_effect=0 AND r.retry_safe=1
  AND NOT EXISTS (SELECT 1 FROM execution_receipts later WHERE later.server_id=r.server_id
      AND later.executor_id=r.executor_id AND later.operation_id=r.operation_id
      AND later.receipt_revision>r.receipt_revision)
  AND tx.dispatch_state='RESOLVED_TERMINAL'
  AND json_extract(tx.last_error,'$.code')='INITIAL_OPEN_FAILED'
  AND json_extract(tx.last_error,'$.possible_effect')=0
  AND NOT EXISTS (SELECT 1 FROM execution_receipts tr WHERE tr.server_id=turn.server_id
      AND tr.executor_id=turn.executor_id AND tr.operation_id=turn.operation_id)
  AND NOT EXISTS (SELECT 1 FROM runtime_results result WHERE result.operation_id=b.operation_id)
  AND NOT EXISTS (SELECT 1 FROM runtime_work_outcomes outcome WHERE outcome.operation_id=b.operation_id);
