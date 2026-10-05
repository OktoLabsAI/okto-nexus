CREATE TABLE execution_inventory_revalidation (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    approved_revision TEXT NOT NULL,
    candidate_ref TEXT NOT NULL,
    current_revision TEXT NOT NULL,
    baseline_json TEXT,
    compatible INTEGER NOT NULL CHECK (compatible IN (0,1)),
    reason TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    PRIMARY KEY(server_id, executor_id, approved_revision, candidate_ref)
);
