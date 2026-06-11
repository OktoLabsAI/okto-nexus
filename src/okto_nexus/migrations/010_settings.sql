-- 010: runtime settings overrides (dashboard Settings screen).
-- Key/value store consulted at serve bootstrap; precedence stays
-- CLI > env > THESE OVERRIDES > defaults, so the CLI remains the
-- authoritative escape hatch and the UI never locks an operator out.
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
