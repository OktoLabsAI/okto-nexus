CREATE TABLE runtime_reset_generation (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    generation INTEGER NOT NULL DEFAULT 0 CHECK (generation >= 0)
);
INSERT INTO runtime_reset_generation(singleton, generation) VALUES (1, 0);
