-- An installation reset selects a new physical Core directory. Keep the
-- identity observed for each generation so a later ledger replacement cannot
-- be mistaken for an empty store. This is not an audit frontier.
CREATE TABLE execution_embedded_store_bindings (
    reset_generation INTEGER PRIMARY KEY CHECK (reset_generation >= 0),
    store_id TEXT NOT NULL,
    bound_at TEXT NOT NULL
);
