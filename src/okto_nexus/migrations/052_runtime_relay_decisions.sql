-- Admission audit for each canonical recipient; not an independent work queue.
CREATE TABLE runtime_relay_decisions (
    result_id TEXT NOT NULL REFERENCES runtime_results(result_id) ON DELETE RESTRICT,
    delivery_id TEXT NOT NULL UNIQUE REFERENCES message_deliveries(delivery_id) ON DELETE RESTRICT,
    operation_id TEXT REFERENCES delivery_outbox(operation_id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK(state IN ('ENQUEUED','BLOCKED','NO_ENDPOINT')),
    reason TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY(result_id,delivery_id)
);
