-- Keep the host proof when an attempt ends before an R4 operation exists.
ALTER TABLE session_interaction_capacity_attempts ADD COLUMN resolution_json TEXT
    CHECK (resolution_json IS NULL OR (state = 'PREPARED' AND resolved_at IS NOT NULL));
