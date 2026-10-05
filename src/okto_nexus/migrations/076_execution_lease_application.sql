-- Correlated Server grants retain their original duration and application proof.
-- Historical rows without this evidence cannot authorize R4 dispatch.
ALTER TABLE execution_leases ADD COLUMN connection_id TEXT;
ALTER TABLE execution_leases ADD COLUMN binding_revision INTEGER;
ALTER TABLE execution_leases ADD COLUMN source_grant_revision INTEGER;
ALTER TABLE execution_leases ADD COLUMN request_digest TEXT;
ALTER TABLE execution_leases ADD COLUMN request_json TEXT;
ALTER TABLE execution_leases ADD COLUMN grant_json TEXT;
ALTER TABLE execution_leases ADD COLUMN scope_json TEXT;
ALTER TABLE execution_leases ADD COLUMN issued_at TEXT;
ALTER TABLE execution_leases ADD COLUMN applied_at TEXT;

CREATE INDEX idx_execution_leases_grant ON execution_leases(grant_id,status);

CREATE TRIGGER execution_lane_fence_leases
AFTER UPDATE OF state,connection_id,connection_generation ON execution_control_lanes
WHEN NEW.state<>'ADMITTED' OR NEW.connection_id<>OLD.connection_id
    OR NEW.connection_generation<>OLD.connection_generation
BEGIN
    UPDATE execution_sessions SET lease_state='SUPERSEDED'
    WHERE server_id=OLD.server_id AND executor_id=OLD.executor_id AND binding_id=OLD.binding_id
      AND lease_state IN ('LEASE_PENDING','ACTIVE')
      AND session_id IN (SELECT session_id FROM execution_leases
          WHERE server_id=OLD.server_id AND executor_id=OLD.executor_id
            AND connection_id=OLD.connection_id AND connection_generation=OLD.connection_generation
            AND status IN ('ISSUED','ACTIVE'));
    UPDATE execution_leases SET status='SUPERSEDED'
    WHERE server_id=OLD.server_id AND executor_id=OLD.executor_id
      AND connection_id=OLD.connection_id AND connection_generation=OLD.connection_generation
      AND status IN ('ISSUED','ACTIVE')
      AND session_id IN (SELECT session_id FROM execution_sessions
          WHERE server_id=OLD.server_id AND executor_id=OLD.executor_id AND binding_id=OLD.binding_id);
END;

CREATE TRIGGER execution_source_grant_revoke_leases
AFTER UPDATE OF revoked_at,revision ON runtime_execution_grants
WHEN NEW.revoked_at IS NOT NULL OR NEW.revision<>OLD.revision
BEGIN
    UPDATE execution_sessions SET lease_state='REVOKED'
    WHERE (server_id,executor_id,session_id) IN
        (SELECT server_id,executor_id,session_id FROM execution_leases
         WHERE grant_id=NEW.grant_id AND status IN ('ISSUED','ACTIVE','SUPERSEDED'));
    UPDATE execution_leases SET status='REVOKED'
    WHERE grant_id=NEW.grant_id AND status IN ('ISSUED','ACTIVE','SUPERSEDED');
END;

CREATE TRIGGER execution_owner_fence_leases
AFTER UPDATE OF generation,owner_instance_id,control_state,revoked_at ON execution_executors
WHEN NEW.generation<>OLD.generation OR NEW.owner_instance_id IS NOT OLD.owner_instance_id
    OR NEW.control_state='DISCONNECTED' OR NEW.revoked_at IS NOT NULL
BEGIN
    UPDATE execution_leases SET status=CASE WHEN NEW.revoked_at IS NULL THEN 'SUPERSEDED' ELSE 'REVOKED' END
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND status IN ('ISSUED','ACTIVE');
    UPDATE execution_sessions SET lease_state=CASE WHEN NEW.revoked_at IS NULL THEN 'SUPERSEDED' ELSE 'REVOKED' END
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id
      AND lease_state IN ('LEASE_PENDING','ACTIVE','SUPERSEDED');
END;
