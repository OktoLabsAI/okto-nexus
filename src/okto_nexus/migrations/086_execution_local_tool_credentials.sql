CREATE TABLE execution_local_tool_credentials (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('REQUESTED','STORED','REMOVED')),
    metadata_json TEXT,
    PRIMARY KEY(server_id,executor_id,session_id),
    UNIQUE(request_id)
);
