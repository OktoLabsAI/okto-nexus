-- R4 execution retains the existing logical delivery and its exclusive claim.
CREATE TABLE execution_domain_deliveries (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    domain_operation_id TEXT NOT NULL REFERENCES delivery_outbox(operation_id),
    PRIMARY KEY (server_id, executor_id, operation_id),
    FOREIGN KEY (server_id, executor_id, operation_id)
        REFERENCES execution_operations(server_id, executor_id, operation_id)
);
CREATE INDEX execution_domain_delivery_source ON execution_domain_deliveries(domain_operation_id);

ALTER TABLE delivery_outbox ADD COLUMN canonical_terminal_operation_id TEXT;
DROP TRIGGER runtime_delivery_capacity_guard;
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
      AND o.terminal_event_id IS NULL AND o.canonical_terminal_operation_id IS NULL;
END;
