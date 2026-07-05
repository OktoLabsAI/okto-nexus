-- Okto Nexus migration 017: HITL approvals queue (spec 2948b2a2).
-- Forward-only. A require_approval policy (new limit_kind in the 016 grammar)
-- intercepts message_create / handoff_create BEFORE persistence: the full
-- re-executable action (use-case kwargs + resolved workspace_id) is serialised
-- into this table in the SAME UoW that returns the pending envelope, so an
-- intercepted action can never be lost (BR1). The human decision via REST is
-- the only trigger that executes (approve) or closes (reject) a row - no
-- background thread. Rows are never deleted; rejected rows keep justification,
-- decided_by and decided_at for audit. status is one of
-- pending | approved | rejected (approved implies executed_result present
-- except during the documented crash window between decision UoWs - BR3).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    action TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    request_payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    decided_by TEXT,
    justification TEXT,
    executed_result TEXT,
    trace_id TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

-- The operator's queue is "oldest pending first" per workspace; the partial
-- index keeps that hot path cheap no matter how much decided history piles up.
CREATE INDEX IF NOT EXISTS idx_approvals_pending ON approvals (workspace_id, created_at) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_approvals_workspace_time ON approvals (workspace_id, created_at);
