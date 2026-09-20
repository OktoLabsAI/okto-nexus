-- Okto Nexus migration 029: harness-connector session/event durability (D10).
-- Two tables. The supervisor's own liveness bookkeeping is IN-MEMORY (D1) -
-- these tables are durability only, never the notification path:
--   * harness_sessions - one durable row per HarnessSession the supervisor
--     opened (audit/replay; a row left RUNNING after an unclean process exit
--     is expected and is NOT proof of liveness).
--   * harness_events - every HarnessEvent a connector emitted, persisted
--     AFTER it was already fanned out in-memory, with native_event carried
--     VERBATIM (the audit trail that makes the no-polling push claim
--     checkable after the fact - see docs/design/0004-harness-integrations.md
--     D10). sequence is monotonic PER session_id, assigned at write time.
-- NOTE: each statement must terminate with ';' on its final line (line-based
-- migration splitter); do not embed ';' inside literals.

CREATE TABLE IF NOT EXISTS harness_sessions (
    session_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    owning_agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    capabilities TEXT NOT NULL,
    metadata TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_harness_sessions_status
ON harness_sessions (status);

CREATE INDEX IF NOT EXISTS idx_harness_sessions_owning_agent
ON harness_sessions (owning_agent_id);

CREATE TABLE IF NOT EXISTS harness_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES harness_sessions(session_id) ON DELETE CASCADE,
    harness_kind TEXT NOT NULL,
    kind TEXT NOT NULL,
    native_event TEXT NOT NULL,
    payload TEXT,
    thread_id TEXT,
    turn_id TEXT,
    occurred_at TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (session_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_harness_events_session_sequence
ON harness_events (session_id, sequence);
