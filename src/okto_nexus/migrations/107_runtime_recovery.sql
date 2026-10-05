ALTER TABLE runtime_policy_defaults ADD COLUMN automatic_recovery INTEGER NOT NULL DEFAULT 1 CHECK(automatic_recovery IN (0,1));
CREATE TABLE runtime_recovery_events (
 id INTEGER PRIMARY KEY, executor_id TEXT NOT NULL, created_at TEXT NOT NULL,
 code TEXT NOT NULL, message TEXT NOT NULL
);
CREATE TABLE runtime_pending_deliveries (
 delivery_id TEXT PRIMARY KEY REFERENCES message_deliveries(delivery_id),
 context_json TEXT NOT NULL, authorization_revision TEXT NOT NULL,
 created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'waiting', attempts INTEGER NOT NULL DEFAULT 0,
 reason TEXT, result_source_json TEXT
);
