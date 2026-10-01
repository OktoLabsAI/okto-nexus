-- Preserve the approved boot revision and owner through the opening fence.
ALTER TABLE execution_operations ADD COLUMN boot_authority_json TEXT;
