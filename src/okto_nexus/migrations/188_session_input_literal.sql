ALTER TABLE session_interaction_inputs ADD COLUMN literal INTEGER NOT NULL DEFAULT 0 CHECK(literal IN (0, 1));

-- Older dispatchers ignore the literal flag. Keep their attempted plain linkage atomic.
CREATE TRIGGER session_interaction_literal_operation
BEFORE UPDATE OF operation_id ON session_interaction_inputs
WHEN NEW.literal=1 AND NEW.operation_id IS NOT NULL AND NEW.operation_id IS NOT OLD.operation_id
AND NOT EXISTS (
    SELECT 1 FROM execution_operations
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id
      AND session_id=NEW.session_id AND operation_id=NEW.operation_id AND action='turn.submit'
      AND json_type(semantic_payload, '$.payload.literal')='true'
)
BEGIN
    SELECT RAISE(ABORT, 'Literal input requires a literal turn operation');
END;
