-- Creator origin is immutable provenance; no session credentials or authority.
-- Historical rows intentionally have no entry and use the missing fallback.
CREATE TABLE execution_handoff_origins (
    handoff_id TEXT PRIMARY KEY REFERENCES handoffs(handoff_id) ON DELETE CASCADE,
    schema_version INTEGER NOT NULL CHECK(schema_version=1),
    source_kind TEXT NOT NULL CHECK(source_kind IN ('runtime','mcp','missing')),
    source_session_key TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    CHECK((source_kind='missing')=(source_session_key=''))
);
