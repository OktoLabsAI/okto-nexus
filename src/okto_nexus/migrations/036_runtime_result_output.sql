ALTER TABLE harness_events ADD COLUMN output_text TEXT;
ALTER TABLE harness_events ADD COLUMN output_snapshot INTEGER NOT NULL DEFAULT 0 CHECK(output_snapshot IN (0,1));
ALTER TABLE runtime_results ADD COLUMN output_text TEXT NOT NULL DEFAULT '';
ALTER TABLE runtime_results ADD COLUMN output_truncated INTEGER NOT NULL DEFAULT 0 CHECK(output_truncated IN (0,1));
ALTER TABLE runtime_results ADD COLUMN output_event_count INTEGER NOT NULL DEFAULT 0;
