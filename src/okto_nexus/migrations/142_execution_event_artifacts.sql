CREATE TABLE execution_event_artifacts (
 artifact_id TEXT PRIMARY KEY,
 server_id TEXT NOT NULL,
 executor_id TEXT NOT NULL,
 session_id TEXT NOT NULL,
 stream_epoch TEXT NOT NULL,
 sequence INTEGER NOT NULL,
 binding_id TEXT NOT NULL,
 agent_id TEXT NOT NULL,
 workspace_id TEXT NOT NULL,
 reference_json TEXT NOT NULL,
 storage_path TEXT,
 size_bytes INTEGER NOT NULL,
 updated_at REAL NOT NULL
);
CREATE TABLE execution_event_artifact_chunks (
 artifact_id TEXT NOT NULL REFERENCES execution_event_artifacts(artifact_id) ON DELETE CASCADE,
 offset INTEGER NOT NULL,
 content BLOB NOT NULL,
 PRIMARY KEY(artifact_id,offset)
);
