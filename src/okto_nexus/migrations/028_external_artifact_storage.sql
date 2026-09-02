-- Okto Nexus migration 028: move artifact payloads out of SQLite.
-- The artifacts table remains a minimal searchable/authorization catalog;
-- payload bytes and free-form metadata live behind the ArtifactStore port.

ALTER TABLE artifacts ADD COLUMN storage_path TEXT;

ALTER TABLE artifacts ADD COLUMN storage_kind TEXT CHECK (storage_kind IN ('inline', 'path'));

ALTER TABLE artifacts ADD COLUMN filename TEXT;

ALTER TABLE artifacts ADD COLUMN media_type TEXT;

CREATE INDEX idx_artifacts_storage_path ON artifacts (storage_path);

-- Keep dashboard pagination/date filtering index-backed both globally and
-- inside the workspace scope selected by the operator.
CREATE INDEX idx_artifacts_created_at
ON artifacts (created_at DESC, artifact_id DESC);

CREATE INDEX idx_artifacts_workspace_created_at
ON artifacts (workspace_id, created_at DESC, artifact_id DESC);
