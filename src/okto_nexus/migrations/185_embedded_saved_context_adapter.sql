-- Capture retirement evidence for multiple managed native adapters.
ALTER TABLE embedded_codex_saved_contexts RENAME TO embedded_saved_contexts;
ALTER TABLE embedded_saved_contexts ADD COLUMN adapter_id TEXT NOT NULL DEFAULT 'codex_app_server'
    CHECK (adapter_id IN ('codex_app_server', 'claude_stream'));
