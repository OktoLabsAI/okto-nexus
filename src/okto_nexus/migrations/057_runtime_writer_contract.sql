-- Store-wide writer contract. Activation is owned by the runtime dispatcher.
-- Markers are registered by the connection factory; payload identity cannot set them.
-- pragma_function_list avoids an unknown-function error for legacy, never-activated stores.
CREATE TABLE runtime_writer_contract (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    required_contract INTEGER NOT NULL DEFAULT 0 CHECK(required_contract>=0),
    admission_enabled INTEGER NOT NULL DEFAULT 0 CHECK(admission_enabled IN (0,1)),
    owner_id TEXT,
    owner_epoch INTEGER
);
INSERT INTO runtime_writer_contract(singleton) VALUES(1);

CREATE TRIGGER runtime_writer_messages_insert
BEFORE INSERT ON messages
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_messages_update
BEFORE UPDATE ON messages
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_messages_delete
BEFORE DELETE ON messages
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_message_deliveries_insert
BEFORE INSERT ON message_deliveries
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_message_deliveries_update
BEFORE UPDATE ON message_deliveries
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_message_deliveries_delete
BEFORE DELETE ON message_deliveries
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_handoffs_insert
BEFORE INSERT ON handoffs
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_handoffs_update
BEFORE UPDATE ON handoffs
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_handoffs_delete
BEFORE DELETE ON handoffs
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_message_admission
BEFORE INSERT ON messages
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND (SELECT admission_enabled FROM runtime_writer_contract WHERE singleton=1)
     <> EXISTS(SELECT 1 FROM pragma_function_list
               WHERE name='nexus_runtime_admission_on' AND builtin=0 AND narg=0)
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_mode_mismatch');
END;

CREATE TRIGGER runtime_writer_agents_insert
BEFORE INSERT ON agents
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_agents_update
BEFORE UPDATE ON agents
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_agents_delete
BEFORE DELETE ON agents
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_sessions_insert
BEFORE INSERT ON sessions
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_sessions_update
BEFORE UPDATE ON sessions
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_sessions_delete
BEFORE DELETE ON sessions
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_harness_sessions_insert
BEFORE INSERT ON harness_sessions
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_harness_sessions_update
BEFORE UPDATE ON harness_sessions
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_harness_sessions_delete
BEFORE DELETE ON harness_sessions
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_harness_events_insert
BEFORE INSERT ON harness_events
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_harness_events_update
BEFORE UPDATE ON harness_events
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;

CREATE TRIGGER runtime_writer_harness_events_delete
BEFORE DELETE ON harness_events
WHEN (SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>0
 AND ((SELECT required_contract FROM runtime_writer_contract WHERE singleton=1)>1
      OR NOT EXISTS(SELECT 1 FROM pragma_function_list
                    WHERE name='nexus_runtime_writer_v1' AND builtin=0 AND narg=0))
BEGIN
    SELECT RAISE(ABORT, 'runtime_writer_incompatible');
END;
