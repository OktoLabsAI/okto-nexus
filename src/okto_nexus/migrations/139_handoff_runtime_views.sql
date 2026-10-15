-- Bounded operator history; no payload or authority duplicated into a read model.
CREATE INDEX handoff_runtime_attempts_agent_history
    ON handoff_runtime_attempts(agent_id,updated_at DESC,attempt_id DESC);
CREATE INDEX handoff_runtime_attempts_recent ON handoff_runtime_attempts(updated_at DESC,attempt_id DESC);
CREATE INDEX handoff_broadcast_recent ON handoffs(created_at DESC,handoff_id DESC)
    WHERE CASE WHEN json_valid(target) THEN json_extract(target,'$.strategy') END='broadcast';
