-- Pending membership follows the durable flags in the same transaction.
-- The implicit rowid suffix preserves bounded cursor paging within each scope.
CREATE INDEX idx_execution_local_publications_pending
    ON execution_local_publications(server_id, executor_id) WHERE terminal=0;
CREATE INDEX idx_execution_local_streams_pending
    ON execution_local_streams(server_id, executor_id) WHERE drained=0;
CREATE INDEX idx_execution_local_streams_agent_pending
    ON execution_local_streams(server_id, executor_id, agent_id) WHERE drained=0;
