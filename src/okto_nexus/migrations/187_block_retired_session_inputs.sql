-- A terminal session cannot send queued inputs. Leave admitted operations and their receipts to reconciliation.
CREATE TRIGGER session_interaction_block_retired_inputs
AFTER UPDATE OF lifecycle_state ON execution_sessions
WHEN NEW.lifecycle_state IN ('CLOSED', 'FAILED') AND NEW.lifecycle_state <> OLD.lifecycle_state
BEGIN
    UPDATE session_interaction_inputs
    SET status='BLOCKED_SESSION', input_revision=input_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id
      AND status='QUEUED' AND operation_id IS NULL AND possible_effect=0;

    UPDATE session_interaction_queues SET revision=revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id
      AND changes()>0;
END;

-- Invalidate cursors for older queues before changing the matching inputs.
UPDATE session_interaction_queues AS q SET revision=revision+1
WHERE EXISTS (
    SELECT 1 FROM session_interaction_inputs i
    JOIN execution_sessions s USING (server_id, executor_id, session_id)
    WHERE i.server_id=q.server_id AND i.executor_id=q.executor_id AND i.session_id=q.session_id
      AND i.status='QUEUED' AND i.operation_id IS NULL AND i.possible_effect=0
      AND s.lifecycle_state IN ('CLOSED', 'FAILED')
);

UPDATE session_interaction_inputs AS i SET status='BLOCKED_SESSION', input_revision=input_revision+1
WHERE status='QUEUED' AND operation_id IS NULL AND possible_effect=0
  AND EXISTS (
    SELECT 1 FROM execution_sessions s
    WHERE s.server_id=i.server_id AND s.executor_id=i.executor_id AND s.session_id=i.session_id
      AND s.lifecycle_state IN ('CLOSED', 'FAILED')
);
