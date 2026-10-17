-- A terminal checkpoint is written only after Core resource/stream proof.
-- Existing history deliberately remains unverified for resumable backfill.
ALTER TABLE execution_sessions ADD COLUMN local_retirement_json TEXT
    CHECK (local_retirement_json IS NULL OR
        (json_valid(local_retirement_json) AND json_extract(local_retirement_json,'$.version') IS 1));
ALTER TABLE execution_sessions ADD COLUMN local_retirement_revision INTEGER NOT NULL DEFAULT 0
    CHECK (local_retirement_revision>=0);
CREATE INDEX idx_execution_sessions_local_pending
    ON execution_sessions(server_id,executor_id) WHERE local_retirement_json IS NULL;
CREATE INDEX idx_execution_local_publications_session_pending
    ON execution_local_publications(server_id,executor_id,session_id) WHERE terminal=0;

-- Any new Server-side obligation invalidates the checkpoint atomically.
CREATE TRIGGER execution_local_retirement_session_changed
AFTER UPDATE OF server_id,executor_id,session_id,open_operation_id,owner_generation,lifecycle_state,lease_state,stream_epoch
ON execution_sessions
WHEN (
    NEW.server_id<>OLD.server_id OR NEW.executor_id<>OLD.executor_id OR NEW.session_id<>OLD.session_id OR
    NEW.open_operation_id<>OLD.open_operation_id OR NEW.owner_generation<>OLD.owner_generation OR
    NEW.lifecycle_state IS NOT OLD.lifecycle_state OR NEW.lease_state IS NOT OLD.lease_state OR
    NEW.stream_epoch IS NOT OLD.stream_epoch)
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;

CREATE TRIGGER execution_local_retirement_operation_added AFTER INSERT ON execution_operations
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;
CREATE TRIGGER execution_local_retirement_publication_added AFTER INSERT ON execution_local_publications
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;
CREATE TRIGGER execution_local_retirement_publication_pending AFTER UPDATE OF terminal ON execution_local_publications
WHEN NEW.terminal=0
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;
CREATE TRIGGER execution_local_retirement_stream_added AFTER INSERT ON execution_local_streams
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;
CREATE TRIGGER execution_local_retirement_stream_changed AFTER UPDATE ON execution_local_streams
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;
CREATE TRIGGER execution_local_retirement_receipt_added AFTER INSERT ON execution_receipts
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=(
        SELECT session_id FROM execution_operations
        WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND operation_id=NEW.operation_id);
END;
CREATE TRIGGER execution_local_retirement_watermark_added AFTER INSERT ON execution_event_watermarks
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;
CREATE TRIGGER execution_local_retirement_event_added AFTER INSERT ON execution_event_ingress
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;
CREATE TRIGGER execution_local_retirement_watermark_changed AFTER UPDATE ON execution_event_watermarks
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;

-- Release projections also unblock domain delivery ordering. Removing or
-- replacing their evidence makes the session pending again, even when its
-- native resource was already released. Recovery must repair from Core proof.
CREATE TRIGGER execution_local_retirement_delivery_release_removed AFTER DELETE ON execution_delivery_releases
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=OLD.server_id AND executor_id=OLD.executor_id AND session_id=OLD.session_id;
END;
CREATE TRIGGER execution_local_retirement_delivery_release_changed AFTER UPDATE ON execution_delivery_releases
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE (server_id=OLD.server_id AND executor_id=OLD.executor_id AND session_id=OLD.session_id)
       OR (server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id);
END;
