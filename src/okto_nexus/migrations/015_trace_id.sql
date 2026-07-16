-- Okto Nexus migration 015: trace_id columns for trajectory correlation (I1).
-- Forward-only. Feature-flagged (feature_trace, default OFF): the columns are
-- nullable, so every pre-existing row and every flag-OFF write stays NULL and
-- nothing changes for deployments that never opt in.
-- Events carry the trace inside their JSON payload (no events column): the
-- event log filters payload keys at the application layer, same as handoff_id.
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

ALTER TABLE messages ADD COLUMN trace_id TEXT;

ALTER TABLE handoffs ADD COLUMN trace_id TEXT;

-- Partial indexes: flag-OFF rows (trace_id NULL) cost nothing; trace lookups
-- are workspace-scoped like every other read path.
CREATE INDEX IF NOT EXISTS idx_messages_trace
    ON messages (workspace_id, trace_id) WHERE trace_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_handoffs_trace
    ON handoffs (workspace_id, trace_id) WHERE trace_id IS NOT NULL;
