-- Capability material is returned once. Persist only its hash and authority.
ALTER TABLE execution_session_capabilities ADD COLUMN actor_agent_id TEXT REFERENCES agents(agent_id);
ALTER TABLE execution_session_capabilities ADD COLUMN request_id TEXT;
ALTER TABLE execution_session_capabilities ADD COLUMN request_digest TEXT;
ALTER TABLE execution_session_capabilities ADD COLUMN scope_json TEXT;
ALTER TABLE execution_session_capabilities ADD COLUMN source_grant_id TEXT REFERENCES runtime_execution_grants(grant_id);
ALTER TABLE execution_session_capabilities ADD COLUMN source_grant_revision INTEGER;
ALTER TABLE execution_session_capabilities ADD COLUMN issued_at TEXT;
ALTER TABLE execution_session_capabilities ADD COLUMN replaced_by TEXT;

CREATE UNIQUE INDEX idx_execution_capability_request
ON execution_session_capabilities(server_id,actor_agent_id,request_id)
WHERE request_id IS NOT NULL;

CREATE UNIQUE INDEX idx_execution_capability_live_audience
ON execution_session_capabilities(server_id,executor_id,session_id,audience)
WHERE revoked_at IS NULL AND scope_json IS NOT NULL;

CREATE TRIGGER execution_source_grant_revoke_capabilities
AFTER UPDATE OF revoked_at,revision ON runtime_execution_grants
WHEN NEW.revoked_at IS NOT NULL OR NEW.revision<>OLD.revision
BEGIN
    UPDATE execution_session_capabilities SET revoked_at=COALESCE(NEW.revoked_at,strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    WHERE source_grant_id=NEW.grant_id AND revoked_at IS NULL;
END;
