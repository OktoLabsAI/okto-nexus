-- No-stream checkpoints depend on positive refusal/capacity evidence. Changes
-- invalidate them in the same transaction, as stream changes already do.
CREATE TRIGGER execution_local_retirement_operation_changed
AFTER UPDATE OF action,intent_hash,semantic_payload,expected_revisions_json,admission_state ON execution_operations
WHEN NEW.action IS NOT OLD.action OR NEW.intent_hash IS NOT OLD.intent_hash
 OR NEW.semantic_payload IS NOT OLD.semantic_payload OR NEW.expected_revisions_json IS NOT OLD.expected_revisions_json
 OR NEW.admission_state IS NOT OLD.admission_state
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;
CREATE TRIGGER execution_local_retirement_operation_removed AFTER DELETE ON execution_operations
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=OLD.server_id AND executor_id=OLD.executor_id AND session_id=OLD.session_id;
END;
CREATE TRIGGER execution_local_retirement_receipt_removed AFTER DELETE ON execution_receipts
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=OLD.server_id AND executor_id=OLD.executor_id AND session_id=(
        SELECT session_id FROM execution_operations WHERE server_id=OLD.server_id
        AND executor_id=OLD.executor_id AND operation_id=OLD.operation_id);
END;
CREATE TRIGGER execution_local_retirement_receipt_changed AFTER UPDATE ON execution_receipts
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE (server_id=OLD.server_id AND executor_id=OLD.executor_id AND session_id=(
        SELECT session_id FROM execution_operations WHERE server_id=OLD.server_id
        AND executor_id=OLD.executor_id AND operation_id=OLD.operation_id))
       OR (server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=(
        SELECT session_id FROM execution_operations WHERE server_id=NEW.server_id
        AND executor_id=NEW.executor_id AND operation_id=NEW.operation_id));
END;
CREATE TRIGGER execution_local_retirement_dispatch_changed
AFTER UPDATE OF dispatch_state,last_error ON execution_dispatch_outbox
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND open_operation_id=NEW.operation_id;
END;
CREATE TRIGGER execution_local_retirement_dispatch_removed AFTER DELETE ON execution_dispatch_outbox
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=OLD.server_id AND executor_id=OLD.executor_id AND open_operation_id=OLD.operation_id;
END;
CREATE TRIGGER execution_local_retirement_denial_added AFTER INSERT ON execution_session_containment
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;
CREATE TRIGGER execution_local_retirement_denial_changed AFTER UPDATE ON execution_session_containment
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE (server_id=OLD.server_id AND executor_id=OLD.executor_id AND session_id=OLD.session_id)
       OR (server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id);
END;
CREATE TRIGGER execution_local_retirement_denial_removed AFTER DELETE ON execution_session_containment
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=OLD.server_id AND executor_id=OLD.executor_id AND session_id=OLD.session_id;
END;
CREATE TRIGGER execution_local_retirement_capacity_added AFTER INSERT ON execution_capacity_admissions
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id;
END;
CREATE TRIGGER execution_local_retirement_capacity_changed AFTER UPDATE ON execution_capacity_admissions
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE (server_id=OLD.server_id AND executor_id=OLD.executor_id AND session_id=OLD.session_id)
       OR (server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id);
END;
CREATE TRIGGER execution_local_retirement_capacity_removed AFTER DELETE ON execution_capacity_admissions
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=OLD.server_id AND executor_id=OLD.executor_id AND session_id=OLD.session_id;
END;
CREATE TRIGGER execution_local_retirement_publication_removed AFTER DELETE ON execution_local_publications
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE server_id=OLD.server_id AND executor_id=OLD.executor_id AND session_id=OLD.session_id;
END;
CREATE TRIGGER execution_local_retirement_publication_identity_changed
AFTER UPDATE OF binding_json,server_id,executor_id,session_id,operation_id ON execution_local_publications
BEGIN
    UPDATE execution_sessions SET local_retirement_json=NULL,local_retirement_revision=local_retirement_revision+1
    WHERE (server_id=OLD.server_id AND executor_id=OLD.executor_id AND session_id=OLD.session_id)
       OR (server_id=NEW.server_id AND executor_id=NEW.executor_id AND session_id=NEW.session_id);
END;
