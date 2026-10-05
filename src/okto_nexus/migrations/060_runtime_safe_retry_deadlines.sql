ALTER TABLE delivery_outbox ADD COLUMN next_attempt_at TEXT;
ALTER TABLE delivery_outbox ADD COLUMN retry_basis TEXT;
CREATE INDEX idx_runtime_delivery_retry_due ON delivery_outbox(next_attempt_at)
    WHERE status='RETRY_WAIT' AND reconciliation_id IS NULL;
ALTER TABLE runtime_delivery_attempt_events ADD COLUMN next_attempt_at TEXT;
ALTER TABLE runtime_delivery_attempt_events ADD COLUMN retry_basis TEXT;

DROP TRIGGER runtime_delivery_attempt_observed;
CREATE TRIGGER runtime_delivery_attempt_observed AFTER UPDATE ON delivery_outbox
WHEN COALESCE(NEW.attempt_id,OLD.attempt_id) IS NOT NULL AND (
    NEW.attempt_id IS NOT OLD.attempt_id OR NEW.status IS NOT OLD.status OR
    NEW.owner_epoch IS NOT OLD.owner_epoch OR NEW.endpoint_id IS NOT OLD.endpoint_id OR
    NEW.runtime_session_id IS NOT OLD.runtime_session_id OR NEW.ack_level IS NOT OLD.ack_level OR
    NEW.reason IS NOT OLD.reason OR NEW.native_thread_id IS NOT OLD.native_thread_id OR
    NEW.native_turn_id IS NOT OLD.native_turn_id OR NEW.terminal_event_id IS NOT OLD.terminal_event_id OR
    NEW.next_attempt_at IS NOT OLD.next_attempt_at OR NEW.retry_basis IS NOT OLD.retry_basis)
BEGIN
    INSERT INTO runtime_delivery_attempt_events (
        operation_id,attempt_id,owner_epoch,endpoint_id,runtime_session_id,state,
        ack_level,reason,native_thread_id,native_turn_id,terminal_event_id,occurred_at,provenance,
        next_attempt_at,retry_basis)
    VALUES (NEW.operation_id,COALESCE(NEW.attempt_id,OLD.attempt_id),
        COALESCE(NEW.owner_epoch,OLD.owner_epoch),NEW.endpoint_id,NEW.runtime_session_id,
        NEW.status,NEW.ack_level,NEW.reason,NEW.native_thread_id,NEW.native_turn_id,
        NEW.terminal_event_id,NEW.updated_at,'observed_transition',NEW.next_attempt_at,NEW.retry_basis);
END;
