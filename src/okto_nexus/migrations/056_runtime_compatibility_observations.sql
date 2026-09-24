-- Native observations are server-owned, separate from caller metadata.
ALTER TABLE harness_sessions ADD COLUMN compatibility_report TEXT NOT NULL DEFAULT '{}'
    CHECK(json_valid(compatibility_report));
