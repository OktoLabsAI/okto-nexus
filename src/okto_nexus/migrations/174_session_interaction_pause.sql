-- A pause follows the canonical session until an authorized explicit resume.
ALTER TABLE session_interaction_queues ADD COLUMN paused_owner_generation INTEGER
    CHECK (paused_owner_generation IS NULL OR
        (typeof(paused_owner_generation) = 'integer' AND paused_owner_generation >= 1));
