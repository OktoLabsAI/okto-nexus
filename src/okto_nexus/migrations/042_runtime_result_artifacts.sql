ALTER TABLE artifacts ADD COLUMN reader_agent_ids TEXT CHECK(reader_agent_ids IS NULL OR (json_valid(reader_agent_ids) AND json_type(reader_agent_ids)='array'));
ALTER TABLE runtime_results ADD COLUMN output_artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE RESTRICT;
ALTER TABLE runtime_results ADD COLUMN artifact_reserved_bytes INTEGER NOT NULL DEFAULT 0 CHECK(artifact_reserved_bytes >= 0);
CREATE INDEX runtime_results_artifact_reservations ON runtime_results(result_id,operation_id,artifact_reserved_bytes) WHERE artifact_reserved_bytes > 0;
