-- A denied renewal creates an obligation, never evidence of a stopped process.
CREATE TABLE execution_session_containment (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    owner_generation INTEGER NOT NULL CHECK(owner_generation >= 1),
    opening_operation_id TEXT NOT NULL,
    opening_intent_hash TEXT NOT NULL,
    request_json TEXT NOT NULL CHECK(json_valid(request_json)),
    state TEXT NOT NULL DEFAULT 'REQUESTED' CHECK(state IN ('REQUESTED','RELEASED')),
    release_proof_json TEXT CHECK(release_proof_json IS NULL OR json_valid(release_proof_json)),
    recorded_at TEXT NOT NULL,
    released_at TEXT,
    PRIMARY KEY(server_id,executor_id,session_id,owner_generation),
    FOREIGN KEY(server_id,executor_id,session_id) REFERENCES execution_sessions(server_id,executor_id,session_id),
    FOREIGN KEY(server_id,executor_id,opening_operation_id) REFERENCES execution_operations(server_id,executor_id,operation_id),
    CHECK((state='REQUESTED' AND release_proof_json IS NULL AND released_at IS NULL)
        OR (state='RELEASED' AND release_proof_json IS NOT NULL AND released_at IS NOT NULL))
);
CREATE INDEX execution_session_containment_pending
    ON execution_session_containment(server_id,executor_id,state,recorded_at);
