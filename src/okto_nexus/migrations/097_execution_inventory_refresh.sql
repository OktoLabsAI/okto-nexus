CREATE TABLE execution_inventory_refresh (
    server_id TEXT NOT NULL,
    actor_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    client_intent_id TEXT NOT NULL,
    refresh_id TEXT NOT NULL UNIQUE,
    executor_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    delivery_id TEXT,
    completed_sequence INTEGER,
    PRIMARY KEY(server_id,actor_agent_id,client_intent_id),
    FOREIGN KEY(server_id,executor_id) REFERENCES execution_executors(server_id,executor_id)
);
CREATE INDEX idx_inventory_refresh_pending ON execution_inventory_refresh(server_id,executor_id)
    WHERE completed_sequence IS NULL;
CREATE TABLE execution_inventory_refresh_deliveries (
    delivery_id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    producer_instance_id TEXT NOT NULL,
    connection_generation INTEGER NOT NULL,
    baseline_sequence INTEGER NOT NULL,
    completed_sequence INTEGER,
    FOREIGN KEY(server_id,executor_id) REFERENCES execution_executors(server_id,executor_id)
);
CREATE INDEX idx_inventory_refresh_delivery ON execution_inventory_refresh_deliveries(
    server_id,executor_id,producer_instance_id,connection_generation)
    WHERE completed_sequence IS NULL;
