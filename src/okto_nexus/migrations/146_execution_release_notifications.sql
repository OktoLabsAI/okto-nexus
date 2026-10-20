-- A resource release is not a native terminal result. Its caller notification
-- has separate provenance and cannot authorize replay or result relay.
CREATE TABLE execution_release_notifications (
    domain_operation_id TEXT PRIMARY KEY REFERENCES delivery_outbox(operation_id),
    message_id TEXT UNIQUE REFERENCES messages(message_id),
    state TEXT NOT NULL CHECK(state IN ('PENDING','PUBLISHED','HISTORICAL')),
    created_at TEXT NOT NULL,
    CHECK((state='PUBLISHED' AND message_id IS NOT NULL)
       OR (state IN ('PENDING','HISTORICAL') AND message_id IS NULL))
);
CREATE INDEX execution_release_notifications_pending
ON execution_release_notifications(created_at,domain_operation_id) WHERE state='PENDING';
-- An upgrade must not send unsolicited notifications for old conversations.
INSERT INTO execution_release_notifications(domain_operation_id,state,created_at)
SELECT domain_operation_id,'HISTORICAL',created_at FROM execution_delivery_releases;
