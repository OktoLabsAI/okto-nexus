-- A promoted control binds the exact effect confirmed by its original author.
ALTER TABLE session_interaction_controls ADD COLUMN confirmed_effect_revision TEXT
    CHECK (confirmed_effect_revision IS NULL OR length(confirmed_effect_revision) BETWEEN 1 AND 160);
