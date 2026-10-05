-- A RESERVED row is recoverable only when its known connection owner is fenced.
ALTER TABLE execution_dispatch_outbox ADD COLUMN reservation_owner TEXT;
ALTER TABLE execution_dispatch_outbox ADD COLUMN reservation_generation INTEGER;
CREATE INDEX idx_execution_dispatch_owner ON execution_dispatch_outbox
    (server_id,executor_id,reservation_owner,reservation_generation,dispatch_state);
