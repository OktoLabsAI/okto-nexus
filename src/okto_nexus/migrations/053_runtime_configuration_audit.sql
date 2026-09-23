-- Extend the existing authorization audit; never store profile/secret values.
ALTER TABLE runtime_access_audit ADD COLUMN resource_kind TEXT;
ALTER TABLE runtime_access_audit ADD COLUMN resource_id TEXT;
ALTER TABLE runtime_access_audit ADD COLUMN old_revision INTEGER;
ALTER TABLE runtime_access_audit ADD COLUMN new_revision INTEGER;
ALTER TABLE runtime_access_audit ADD COLUMN changed_fields TEXT;
CREATE INDEX idx_runtime_configuration_audit ON runtime_access_audit(resource_kind,resource_id,audit_id);
