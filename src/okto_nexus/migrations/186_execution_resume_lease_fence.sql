-- The retained proof authorizes only the two edges of the same transport resume.
-- There is no executor owner between those edges, so no new dispatch can occur.
DROP TRIGGER execution_owner_fence_leases;
CREATE TRIGGER execution_owner_fence_leases
AFTER UPDATE OF generation,owner_instance_id,control_state,revoked_at ON execution_executors
WHEN (NEW.generation<>OLD.generation OR NEW.owner_instance_id IS NOT OLD.owner_instance_id
    OR NEW.control_state='DISCONNECTED' OR NEW.revoked_at IS NOT NULL)
  AND NOT (NEW.kind='remote' AND NEW.generation=OLD.generation
    AND OLD.revoked_at IS NULL AND NEW.revoked_at IS NULL
    AND EXISTS (
        SELECT 1 FROM execution_connection_resumes r
        WHERE r.server_id=NEW.server_id AND r.executor_id=NEW.executor_id
          AND r.connection_generation=NEW.generation AND julianday(r.expires_at)>julianday('now')
          AND ((OLD.control_state='CONTROL_READY' AND OLD.owner_instance_id=r.connection_id
                AND NEW.control_state='DISCONNECTED' AND NEW.owner_instance_id IS NULL)
            OR (OLD.control_state='DISCONNECTED' AND OLD.owner_instance_id IS NULL
                AND NEW.control_state='CONTROL_READY' AND NEW.owner_instance_id=r.connection_id))
    ))
BEGIN
    UPDATE execution_leases SET status=CASE WHEN NEW.revoked_at IS NULL THEN 'SUPERSEDED' ELSE 'REVOKED' END
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND status IN ('ISSUED','ACTIVE');
    UPDATE execution_sessions SET lease_state=CASE WHEN NEW.revoked_at IS NULL THEN 'SUPERSEDED' ELSE 'REVOKED' END
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id
      AND lease_state IN ('LEASE_PENDING','ACTIVE','SUPERSEDED');
END;
