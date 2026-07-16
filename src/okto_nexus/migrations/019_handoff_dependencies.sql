-- Okto Nexus migration 019: handoff dependencies (I5, feature_dag).
-- Forward-only, additive: one row per (dependent, dependency) edge, captured
-- at handoff_create and IMMUTABLE afterwards (no UPDATE path exists). A
-- handoff with no rows here has no dependencies - pre-019 data needs no
-- backfill. Blocked-ness is DERIVED on-read by joining the dependency's
-- current status (nothing is ever materialised on the dependent's row), so
-- this table needs no status column.
-- No declarative FK: ids are validated fail-closed by the application layer
-- at create time (same-workspace existence), and handoffs rows are never
-- deleted by the protocol verbs; an FK would only add per-write overhead.
-- Idempotency is guaranteed at the runner level (schema_migrations ledger
-- records version 019 once).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

-- The composite PK gives the forward lookup (dependencies of X) and free
-- duplicate protection; insertion order (rowid) preserves the caller's
-- depends_on list order for reads.
CREATE TABLE IF NOT EXISTS handoff_dependencies (
    handoff_id TEXT NOT NULL,
    depends_on_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (handoff_id, depends_on_id)
);

-- Reverse index: "who depends on Y" - the synchronous unblock path resolves
-- dependents of a just-COMPLETED (or just-failed) handoff through this.
CREATE INDEX IF NOT EXISTS idx_handoff_deps_reverse
    ON handoff_dependencies (depends_on_id);
