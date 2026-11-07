-- Auxiliary viewing anchors. A fresh blocked report after a gap is a new
-- episode even if nobody queried the old, expired observation in between.
CREATE TABLE observation_attention_anchors (
    observed_instance_id TEXT PRIMARY KEY REFERENCES observation_instances(observed_instance_id) ON DELETE CASCADE,
    generation INTEGER NOT NULL,
    blocked_sequence INTEGER,
    blocked_started_at TEXT,
    CHECK((blocked_sequence IS NULL AND blocked_started_at IS NULL)
       OR (typeof(blocked_sequence)='integer' AND blocked_sequence>0 AND blocked_started_at IS NOT NULL))
);
INSERT INTO observation_attention_anchors
SELECT observed_instance_id,generation,
    CASE WHEN state='blocked' THEN sequence END,
    CASE WHEN state='blocked' THEN received_at END
FROM observation_heads;

CREATE TRIGGER observation_attention_head_insert AFTER INSERT ON observation_heads
BEGIN
    INSERT INTO observation_attention_anchors VALUES(NEW.observed_instance_id,NEW.generation,
        CASE WHEN NEW.state='blocked' THEN NEW.sequence END,
        CASE WHEN NEW.state='blocked' THEN NEW.received_at END)
    ON CONFLICT(observed_instance_id) DO UPDATE SET generation=excluded.generation,
        blocked_sequence=excluded.blocked_sequence,blocked_started_at=excluded.blocked_started_at;
END;

CREATE TRIGGER observation_attention_head_update AFTER UPDATE ON observation_heads
WHEN NEW.sequence<>OLD.sequence OR NEW.generation<>OLD.generation
BEGIN
    INSERT INTO observation_attention_anchors VALUES(NEW.observed_instance_id,NEW.generation,
        CASE WHEN NEW.state='blocked' THEN NEW.sequence END,
        CASE WHEN NEW.state='blocked' THEN NEW.received_at END)
    ON CONFLICT(observed_instance_id) DO UPDATE SET generation=excluded.generation,
        blocked_sequence=CASE WHEN NEW.state='blocked' AND OLD.state='blocked'
            AND NEW.generation=OLD.generation AND NEW.source_revision=OLD.source_revision
            AND OLD.valid_until>NEW.received_at
            AND NOT EXISTS(SELECT 1 FROM observation_tokens WHERE token_id=OLD.publisher_token_id AND revoked_at IS NOT NULL)
            THEN observation_attention_anchors.blocked_sequence ELSE excluded.blocked_sequence END,
        blocked_started_at=CASE WHEN NEW.state='blocked' AND OLD.state='blocked'
            AND NEW.generation=OLD.generation AND NEW.source_revision=OLD.source_revision
            AND OLD.valid_until>NEW.received_at
            AND NOT EXISTS(SELECT 1 FROM observation_tokens WHERE token_id=OLD.publisher_token_id AND revoked_at IS NOT NULL)
            THEN observation_attention_anchors.blocked_started_at ELSE excluded.blocked_started_at END;
END;

CREATE TRIGGER observation_attention_head_delete AFTER DELETE ON observation_heads
BEGIN
    DELETE FROM observation_attention_anchors WHERE observed_instance_id=OLD.observed_instance_id;
END;

-- Completion facts remain in the bounded observational event history, never
-- in the productive result tables. Preserve publisher revocation evidence for
-- as long as its completion event is retained.
CREATE INDEX observation_completion_instance ON events(
    json_extract(payload,'$.observed_instance_id'),event_id)
    WHERE type='observation.completion';
CREATE INDEX observation_completion_publisher ON events(
    json_extract(payload,'$.publisher_token_id'),event_id)
    WHERE type='observation.completion';
