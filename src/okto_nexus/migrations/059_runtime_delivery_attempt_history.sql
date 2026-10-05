-- Observations of transport attempts, never a queue or work authority.
CREATE TABLE runtime_delivery_attempt_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL REFERENCES delivery_outbox(operation_id) ON DELETE RESTRICT,
    attempt_id TEXT NOT NULL,
    owner_epoch INTEGER,
    endpoint_id TEXT NOT NULL,
    runtime_session_id TEXT,
    state TEXT NOT NULL,
    ack_level TEXT NOT NULL,
    reason TEXT,
    native_thread_id TEXT,
    native_turn_id TEXT,
    terminal_event_id TEXT,
    occurred_at TEXT NOT NULL,
    provenance TEXT NOT NULL CHECK(provenance IN ('migration_snapshot','observed_transition'))
);
CREATE INDEX idx_runtime_delivery_attempt_history
    ON runtime_delivery_attempt_events(operation_id, sequence);

-- The previous schema retained only the current attempt. Do not manufacture
-- lost historical attempts or pretend the migration observed their transitions.
INSERT INTO runtime_delivery_attempt_events (
    operation_id,attempt_id,owner_epoch,endpoint_id,runtime_session_id,state,
    ack_level,reason,native_thread_id,native_turn_id,terminal_event_id,occurred_at,provenance)
SELECT operation_id,attempt_id,owner_epoch,endpoint_id,runtime_session_id,status,
    ack_level,reason,native_thread_id,native_turn_id,terminal_event_id,updated_at,'migration_snapshot'
FROM delivery_outbox WHERE attempt_id IS NOT NULL;

CREATE TRIGGER runtime_delivery_attempt_observed AFTER UPDATE ON delivery_outbox
WHEN COALESCE(NEW.attempt_id,OLD.attempt_id) IS NOT NULL AND (
    NEW.attempt_id IS NOT OLD.attempt_id OR NEW.status IS NOT OLD.status OR
    NEW.owner_epoch IS NOT OLD.owner_epoch OR NEW.endpoint_id IS NOT OLD.endpoint_id OR
    NEW.runtime_session_id IS NOT OLD.runtime_session_id OR NEW.ack_level IS NOT OLD.ack_level OR
    NEW.reason IS NOT OLD.reason OR NEW.native_thread_id IS NOT OLD.native_thread_id OR
    NEW.native_turn_id IS NOT OLD.native_turn_id OR NEW.terminal_event_id IS NOT OLD.terminal_event_id)
BEGIN
    INSERT INTO runtime_delivery_attempt_events (
        operation_id,attempt_id,owner_epoch,endpoint_id,runtime_session_id,state,
        ack_level,reason,native_thread_id,native_turn_id,terminal_event_id,occurred_at,provenance)
    VALUES (NEW.operation_id,COALESCE(NEW.attempt_id,OLD.attempt_id),
        COALESCE(NEW.owner_epoch,OLD.owner_epoch),NEW.endpoint_id,NEW.runtime_session_id,
        NEW.status,NEW.ack_level,NEW.reason,NEW.native_thread_id,NEW.native_turn_id,
        NEW.terminal_event_id,NEW.updated_at,'observed_transition');
END;

CREATE TRIGGER runtime_delivery_attempt_no_update BEFORE UPDATE ON runtime_delivery_attempt_events
BEGIN
    SELECT RAISE(ABORT,'runtime_attempt_history_is_immutable');
END;
CREATE TRIGGER runtime_delivery_attempt_no_delete BEFORE DELETE ON runtime_delivery_attempt_events
BEGIN
    SELECT RAISE(ABORT,'runtime_attempt_history_is_immutable');
END;
