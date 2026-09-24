-- Capacity is measured over unresolved logical push reservations, not history.
-- Retain all reservations and operation identities; no destructive backfill.
CREATE INDEX idx_runtime_delivery_capacity
ON message_deliveries(consumer_operation_id)
WHERE consumer_kind='push' AND status='unread';

-- Enforce at the store boundary as well: an already-open writer-v1 connection
-- can still run the old enqueue implementation after this additive upgrade.
CREATE TRIGGER runtime_delivery_capacity_guard
BEFORE INSERT ON delivery_outbox
BEGIN
    SELECT CASE WHEN
        count(*) >= 256
        OR COALESCE(sum(length(CAST(o.envelope AS BLOB))),0)
           + length(CAST(NEW.envelope AS BLOB)) > 4194304
        OR COALESCE(sum(o.actor_agent_id=NEW.actor_agent_id),0) >= 32
        OR COALESCE(sum(o.recipient_agent_id=NEW.recipient_agent_id),0) >= 32
        OR COALESCE(sum(o.workspace_id=NEW.workspace_id),0) >= 128
        THEN RAISE(ABORT, 'runtime_delivery_backpressure') END
    FROM delivery_outbox o JOIN message_deliveries d
      ON d.consumer_operation_id=o.operation_id AND d.consumer_kind='push'
    WHERE d.status='unread' AND o.reconciliation_id IS NULL
      AND o.terminal_event_id IS NULL;
END;
