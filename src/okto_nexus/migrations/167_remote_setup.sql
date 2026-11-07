-- Operator-reviewed remote bootstrap is partial; final Finish receipts stay separate.
CREATE TABLE remote_setup_runs (
    actor_agent_id TEXT NOT NULL,
    setup_run_id TEXT NOT NULL CHECK(length(setup_run_id) BETWEEN 1 AND 100),
    current_review_revision TEXT NOT NULL CHECK(length(current_review_revision)=64),
    bootstrap_review_revision TEXT,
    bootstrap_json TEXT CHECK(bootstrap_json IS NULL OR (json_valid(bootstrap_json) AND length(CAST(bootstrap_json AS BLOB))<=65536)),
    bootstrap_baseline_json TEXT CHECK(bootstrap_baseline_json IS NULL OR json_valid(bootstrap_baseline_json)),
    final_binding_json TEXT CHECK(final_binding_json IS NULL OR json_valid(final_binding_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(actor_agent_id,setup_run_id)
) WITHOUT ROWID;
CREATE TABLE remote_setup_reviews (
    actor_agent_id TEXT NOT NULL,
    setup_run_id TEXT NOT NULL,
    review_revision TEXT NOT NULL CHECK(length(review_revision)=64),
    request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
    previous_review_revision TEXT,
    review_json TEXT NOT NULL CHECK(json_valid(review_json) AND length(CAST(review_json AS BLOB))<=65536),
    created_at TEXT NOT NULL,
    PRIMARY KEY(actor_agent_id,setup_run_id,review_revision),
    FOREIGN KEY(actor_agent_id,setup_run_id) REFERENCES remote_setup_runs(actor_agent_id,setup_run_id)
) WITHOUT ROWID;
CREATE INDEX remote_setup_review_lookup ON remote_setup_reviews(setup_run_id,review_revision);
