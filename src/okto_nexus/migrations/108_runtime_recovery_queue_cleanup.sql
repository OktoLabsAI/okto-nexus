-- Deferred messages have no native side effect. Respect normal inbox cleanup;
-- submitted deliveries retain the existing outbox deletion restrictions.
CREATE TRIGGER runtime_pending_delivery_cleanup
BEFORE DELETE ON message_deliveries
BEGIN
    DELETE FROM runtime_pending_deliveries WHERE delivery_id=OLD.delivery_id;
END;

CREATE INDEX runtime_pending_deliveries_waiting
ON runtime_pending_deliveries(status, attempts, created_at, delivery_id);
