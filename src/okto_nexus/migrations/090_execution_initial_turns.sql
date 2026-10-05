-- A start prompt is a separate durable operation, never an opening payload.
ALTER TABLE execution_client_intents ADD COLUMN initial_turn_json TEXT;
ALTER TABLE execution_operations ADD COLUMN parent_operation_id TEXT;
CREATE INDEX execution_operations_parent ON execution_operations(server_id,executor_id,parent_operation_id);
