-- Preserve the exact Core frame and its connection origin for durable replay.
ALTER TABLE execution_receipts ADD COLUMN source_connection_id TEXT;
ALTER TABLE execution_receipts ADD COLUMN source_connection_generation INTEGER;
ALTER TABLE execution_receipts ADD COLUMN frame_digest TEXT;
ALTER TABLE execution_receipts ADD COLUMN canonical_frame TEXT;
