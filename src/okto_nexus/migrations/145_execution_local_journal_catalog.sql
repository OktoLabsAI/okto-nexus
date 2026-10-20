-- Derived location in the canonical session, never a second ownership ledger.
ALTER TABLE execution_sessions ADD COLUMN local_journal_name TEXT;
CREATE UNIQUE INDEX idx_execution_sessions_local_journal
    ON execution_sessions(server_id,executor_id,local_journal_name)
    WHERE local_journal_name IS NOT NULL;
CREATE INDEX idx_execution_sessions_local_uncatalogued
    ON execution_sessions(server_id,executor_id) WHERE local_journal_name IS NULL;

CREATE TRIGGER execution_local_journal_identity_changed
AFTER UPDATE OF executor_id,session_id ON execution_sessions
WHEN NEW.executor_id IS NOT OLD.executor_id OR NEW.session_id IS NOT OLD.session_id
BEGIN
    UPDATE execution_sessions SET local_journal_name=NULL
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;
