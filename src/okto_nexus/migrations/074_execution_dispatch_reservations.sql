-- Exact pre-send dispatch capacity accounting. Existing rows remain unreserved.
ALTER TABLE execution_dispatch_outbox ADD COLUMN reservation_class TEXT;
ALTER TABLE execution_dispatch_outbox ADD COLUMN reserved_bytes INTEGER NOT NULL DEFAULT 0 CHECK (reserved_bytes >= 0);
ALTER TABLE execution_dispatch_outbox ADD COLUMN reserved_at TEXT;
