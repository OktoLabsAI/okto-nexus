ALTER TABLE harness_events ADD COLUMN origin TEXT NOT NULL DEFAULT 'native' CHECK(origin IN ('native', 'nexus'));
