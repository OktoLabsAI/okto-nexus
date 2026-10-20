-- The host half of a Core/Server audit handshake. This is a candidate
-- frontier only; startup must continue its physical directory audit.
ALTER TABLE execution_embedded_store_bindings ADD COLUMN audit_nonce TEXT;
ALTER TABLE execution_embedded_store_bindings ADD COLUMN audit_revision INTEGER;
ALTER TABLE execution_embedded_store_bindings ADD COLUMN audit_digest TEXT;
ALTER TABLE execution_embedded_store_bindings ADD COLUMN audit_completed_at TEXT;
