-- Okto Nexus migration 021: index for windowed event reads (I7, dec_3fe21a70).
-- Forward-only, INDEX-ONLY: no schema/table changes, no data rewrite. The
-- coordination-health queries (and the pre-existing workspace_event_stats)
-- filter events by workspace_id + created_at, which until now paid a per-
-- workspace scan (only (workspace_id, event_id) and (workspace_id, stream,
-- event_id) existed).
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

CREATE INDEX IF NOT EXISTS idx_events_workspace_created
    ON events (workspace_id, created_at);
