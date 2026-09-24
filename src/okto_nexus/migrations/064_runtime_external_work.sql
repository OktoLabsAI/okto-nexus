-- External Nexus acknowledgements are not native events or native results.
ALTER TABLE runtime_handoff_bindings ADD COLUMN external_session_id TEXT
    REFERENCES sessions(session_id) ON DELETE RESTRICT;
ALTER TABLE runtime_handoff_bindings ADD COLUMN external_secret_binding TEXT;
ALTER TABLE runtime_handoff_bindings ADD COLUMN external_acked_at TEXT;
ALTER TABLE runtime_handoff_bindings ADD COLUMN external_completion_action TEXT
    CHECK(external_completion_action IN ('complete','reject'));
ALTER TABLE delivery_outbox ADD COLUMN external_completed_at TEXT;
CREATE INDEX idx_runtime_external_work_session
    ON runtime_handoff_bindings(external_session_id) WHERE external_session_id IS NOT NULL;

-- Keep legacy work usable, but do not let an already-open pre-064 writer
-- bypass external session proof through its legacy complete/reject handler.
-- Query the marker's presence rather than invoking an unknown SQL function.
CREATE TRIGGER runtime_external_work_handoff_writer
BEFORE UPDATE OF status ON handoffs
WHEN OLD.status='CLAIMED' AND NEW.status IN ('COMPLETED','VERIFYING','REJECTED')
 AND EXISTS(SELECT 1 FROM runtime_handoff_bindings b
            WHERE b.handoff_id=OLD.handoff_id AND b.claim_epoch=OLD.claim_epoch
              AND b.external_session_id IS NOT NULL)
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list
                WHERE name='nexus_runtime_external_work_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_external_work_writer_incompatible');
END;

CREATE TRIGGER runtime_external_work_ack_writer
BEFORE UPDATE OF status ON message_deliveries
WHEN OLD.status<>'read' AND NEW.status='read'
 AND EXISTS(SELECT 1 FROM runtime_handoff_bindings b JOIN delivery_outbox o USING(operation_id)
            WHERE o.delivery_id=OLD.delivery_id AND b.external_session_id IS NOT NULL)
 AND NOT EXISTS(SELECT 1 FROM pragma_function_list
                WHERE name='nexus_runtime_external_work_v1' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_external_work_writer_incompatible');
END;
