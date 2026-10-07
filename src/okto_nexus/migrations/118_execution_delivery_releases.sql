-- Resource release is not a native turn result. Keep its provenance separate.
CREATE TABLE execution_delivery_releases (
    domain_operation_id TEXT PRIMARY KEY REFERENCES delivery_outbox(operation_id),
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    proof_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (server_id,executor_id,operation_id)
        REFERENCES execution_operations(server_id,executor_id,operation_id),
    FOREIGN KEY (server_id,executor_id,session_id)
        REFERENCES execution_sessions(server_id,executor_id,session_id)
);
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
      AND o.terminal_event_id IS NULL AND o.canonical_terminal_operation_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM execution_delivery_releases r WHERE r.domain_operation_id=o.operation_id);
END;
