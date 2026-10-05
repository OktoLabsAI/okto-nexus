-- Reuse the store-wide runtime admission contract, including legacy writers.
-- Only the current owner may publish capture health through the repository CAS.
ALTER TABLE runtime_writer_contract ADD COLUMN capture_available INTEGER NOT NULL DEFAULT 1 CHECK(capture_available IN (0,1));

CREATE TRIGGER runtime_capture_delivery_admission
BEFORE INSERT ON delivery_outbox
WHEN (SELECT capture_available FROM runtime_writer_contract WHERE singleton=1)=0
BEGIN
    SELECT RAISE(ABORT, 'runtime_capture_unavailable');
END;

CREATE TRIGGER runtime_capture_command_admission
BEFORE INSERT ON runtime_commands
WHEN NEW.verb IN ('send_turn','steer')
 AND (SELECT capture_available FROM runtime_writer_contract WHERE singleton=1)=0
BEGIN
    SELECT RAISE(ABORT, 'runtime_capture_unavailable');
END;

CREATE TRIGGER runtime_capture_open_admission
BEFORE INSERT ON runtime_open_requests
WHEN (SELECT capture_available FROM runtime_writer_contract WHERE singleton=1)=0
BEGIN
    SELECT RAISE(ABORT, 'runtime_capture_unavailable');
END;
