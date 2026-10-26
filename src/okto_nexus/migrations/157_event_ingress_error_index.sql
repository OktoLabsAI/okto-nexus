-- Stream health reads only error events (#86). A partial index keeps that read
-- off the full ingress history of an executor.
CREATE INDEX idx_event_ingress_error
    ON execution_event_ingress(server_id,executor_id,session_id,stream_epoch)
    WHERE event_type='error';
