-- Explicit flags preserve existing bounded grants and fail closed in old readers.
-- For unbounded grants, legacy columns contain expired/one-action placeholders.
ALTER TABLE runtime_execution_grants ADD COLUMN no_expiry INTEGER NOT NULL DEFAULT 0 CHECK(no_expiry IN (0,1));
ALTER TABLE runtime_execution_grants ADD COLUMN unlimited_actions INTEGER NOT NULL DEFAULT 0 CHECK(unlimited_actions IN (0,1));
