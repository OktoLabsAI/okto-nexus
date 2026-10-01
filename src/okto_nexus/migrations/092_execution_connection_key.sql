-- Limited bootstrap authority remains attached to the canonical opening.
ALTER TABLE execution_operations ADD COLUMN connection_key_id TEXT;
