-- System disposition is separate from authenticated operator decisions.
CREATE TABLE runtime_handoff_notice_retirements (
    operation_id TEXT PRIMARY KEY REFERENCES delivery_outbox(operation_id),
    message_id TEXT NOT NULL REFERENCES runtime_handoff_notifications(message_id),
    actor_kind TEXT NOT NULL CHECK(actor_kind='system_migration'),
    previous_state TEXT NOT NULL,
    reason TEXT NOT NULL CHECK(reason='competitive_notice_before_send'),
    recorded_at REAL NOT NULL
);
ALTER TABLE handoff_runtime_schedule_scan ADD COLUMN notice_cursor TEXT NOT NULL DEFAULT '';
