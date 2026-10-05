CREATE TABLE runtime_journal_checkpoint (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
    store_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    updated_at TEXT NOT NULL
);

CREATE TABLE runtime_results (
    result_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE REFERENCES harness_events(event_id) ON DELETE RESTRICT,
    runtime_session_id TEXT NOT NULL REFERENCES harness_sessions(session_id) ON DELETE RESTRICT,
    native_thread_id TEXT,
    native_turn_id TEXT,
    payload TEXT NOT NULL,
    publication_state TEXT NOT NULL DEFAULT 'PENDING_AUTHORIZATION',
    captured_at TEXT NOT NULL
);

CREATE INDEX runtime_results_session ON runtime_results(runtime_session_id, captured_at);
