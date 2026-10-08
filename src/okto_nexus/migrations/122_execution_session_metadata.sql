-- Opaque compatibility annotations are session data, never execution authority.
ALTER TABLE execution_sessions ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}';
