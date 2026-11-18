-- Retain launch evidence when the rolling inventory drops the opening snapshot.
-- Older sessions have no recorded build proof from this admission boundary.
ALTER TABLE execution_sessions ADD COLUMN native_launch_build_json TEXT;
