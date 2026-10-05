-- Intent admission must compare the authoritative source rows observed at resolve.
-- Existing preview intents have no guard and cannot be admitted.
ALTER TABLE execution_client_intents ADD COLUMN source_guard_digest TEXT;
