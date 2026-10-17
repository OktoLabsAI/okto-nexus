-- Marks only a completed legacy-file import into Core's physical registry.
-- This does not authorize skipping the startup directory audit.
ALTER TABLE execution_embedded_store_bindings
ADD COLUMN registry_import_complete INTEGER NOT NULL DEFAULT 0
CHECK (registry_import_complete IN (0,1));
