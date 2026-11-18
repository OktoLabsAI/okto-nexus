-- Retain the checked grant even after revocation or removal of the live grant.
ALTER TABLE session_interaction_inputs ADD COLUMN source_grant_id TEXT;
ALTER TABLE session_interaction_inputs ADD COLUMN source_grant_revision INTEGER
    CHECK ((source_grant_id IS NULL AND source_grant_revision IS NULL) OR
           (source_grant_id IS NOT NULL AND typeof(source_grant_revision) = 'integer' AND source_grant_revision >= 1));
