-- Auxiliary operator viewing state; canonical work remains in its source tables.
CREATE TABLE attention_preferences (
    principal TEXT NOT NULL CHECK (principal = 'operator'),
    attention_id TEXT NOT NULL,
    seen_at TEXT,
    snoozed_until TEXT,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (principal, attention_id)
);
CREATE INDEX idx_attention_preferences_updated ON attention_preferences(updated_at, attention_id);

-- Durable transition anchors; backfill time is first stored observation.

CREATE TABLE attention_operation_epochs (
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    state TEXT NOT NULL,
    episode INTEGER NOT NULL CHECK(episode >= 1),
    first_detected_at TEXT NOT NULL,
    last_changed_at TEXT NOT NULL,
    PRIMARY KEY(source_type,source_id)
);
CREATE INDEX attention_parked_delivery ON message_deliveries(status,recipient_agent_id,delivery_id);
CREATE INDEX attention_pending_recovery ON runtime_pending_deliveries(status,delivery_id);

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'message_delivery',row.delivery_id,row.status,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM message_deliveries row;
CREATE TRIGGER attention_message_deliveries_insert AFTER INSERT ON message_deliveries BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('message_delivery',NEW.delivery_id,NEW.status,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state=excluded.state,episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_message_deliveries_state AFTER UPDATE OF status ON message_deliveries WHEN OLD.status IS NOT NEW.status BEGIN UPDATE attention_operation_epochs SET state=NEW.status,episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='message_delivery' AND source_id=NEW.delivery_id; END;
CREATE TRIGGER attention_message_deliveries_delete AFTER DELETE ON message_deliveries BEGIN DELETE FROM attention_operation_epochs WHERE source_type='message_delivery' AND source_id=OLD.delivery_id; END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'runtime_pending_delivery',row.delivery_id,row.status,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM runtime_pending_deliveries row;
CREATE TRIGGER attention_runtime_pending_deliveries_insert AFTER INSERT ON runtime_pending_deliveries BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('runtime_pending_delivery',NEW.delivery_id,NEW.status,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state=excluded.state,episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_runtime_pending_deliveries_state AFTER UPDATE OF status ON runtime_pending_deliveries WHEN OLD.status IS NOT NEW.status BEGIN UPDATE attention_operation_epochs SET state=NEW.status,episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='runtime_pending_delivery' AND source_id=NEW.delivery_id; END;
CREATE TRIGGER attention_runtime_pending_deliveries_delete AFTER DELETE ON runtime_pending_deliveries BEGIN DELETE FROM attention_operation_epochs WHERE source_type='runtime_pending_delivery' AND source_id=OLD.delivery_id; END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'execution_executor',json_array(row.server_id,row.executor_id),row.control_state,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM execution_executors row;
CREATE TRIGGER attention_execution_executors_insert AFTER INSERT ON execution_executors BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('execution_executor',json_array(NEW.server_id,NEW.executor_id),NEW.control_state,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state=excluded.state,episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_execution_executors_state AFTER UPDATE OF control_state ON execution_executors WHEN OLD.control_state IS NOT NEW.control_state BEGIN UPDATE attention_operation_epochs SET state=NEW.control_state,episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='execution_executor' AND source_id=json_array(NEW.server_id,NEW.executor_id); END;
CREATE TRIGGER attention_execution_executors_delete AFTER DELETE ON execution_executors BEGIN DELETE FROM attention_operation_epochs WHERE source_type='execution_executor' AND source_id=json_array(OLD.server_id,OLD.executor_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'execution_dispatch',json_array(row.server_id,row.executor_id,row.operation_id),row.dispatch_state,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM execution_dispatch_outbox row;
CREATE TRIGGER attention_execution_dispatch_outbox_insert AFTER INSERT ON execution_dispatch_outbox BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('execution_dispatch',json_array(NEW.server_id,NEW.executor_id,NEW.operation_id),NEW.dispatch_state,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state=excluded.state,episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_execution_dispatch_outbox_state AFTER UPDATE OF dispatch_state ON execution_dispatch_outbox WHEN OLD.dispatch_state IS NOT NEW.dispatch_state BEGIN UPDATE attention_operation_epochs SET state=NEW.dispatch_state,episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='execution_dispatch' AND source_id=json_array(NEW.server_id,NEW.executor_id,NEW.operation_id); END;
CREATE TRIGGER attention_execution_dispatch_outbox_delete AFTER DELETE ON execution_dispatch_outbox BEGIN DELETE FROM attention_operation_epochs WHERE source_type='execution_dispatch' AND source_id=json_array(OLD.server_id,OLD.executor_id,OLD.operation_id); END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'runtime_grant_revision',row.grant_id,row.revision,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM runtime_execution_grants row;
CREATE TRIGGER attention_runtime_execution_grants_insert AFTER INSERT ON runtime_execution_grants BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('runtime_grant_revision',NEW.grant_id,NEW.revision,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state=excluded.state,episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_runtime_execution_grants_state AFTER UPDATE OF revision ON runtime_execution_grants WHEN OLD.revision IS NOT NEW.revision BEGIN UPDATE attention_operation_epochs SET state=NEW.revision,episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='runtime_grant_revision' AND source_id=NEW.grant_id; END;
CREATE TRIGGER attention_runtime_execution_grants_delete AFTER DELETE ON runtime_execution_grants BEGIN DELETE FROM attention_operation_epochs WHERE source_type='runtime_grant_revision' AND source_id=OLD.grant_id; END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'runtime_endpoint_revision',row.endpoint_id,json_array(row.revision,row.enabled,row.activation_state),1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM agent_endpoints row;
CREATE TRIGGER attention_agent_endpoints_insert AFTER INSERT ON agent_endpoints BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('runtime_endpoint_revision',NEW.endpoint_id,json_array(NEW.revision,NEW.enabled,NEW.activation_state),1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state=excluded.state,episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_agent_endpoints_state AFTER UPDATE OF revision,enabled,activation_state ON agent_endpoints WHEN json_array(OLD.revision,OLD.enabled,OLD.activation_state) IS NOT json_array(NEW.revision,NEW.enabled,NEW.activation_state) BEGIN UPDATE attention_operation_epochs SET state=json_array(NEW.revision,NEW.enabled,NEW.activation_state),episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='runtime_endpoint_revision' AND source_id=NEW.endpoint_id; END;
CREATE TRIGGER attention_agent_endpoints_delete AFTER DELETE ON agent_endpoints BEGIN DELETE FROM attention_operation_epochs WHERE source_type='runtime_endpoint_revision' AND source_id=OLD.endpoint_id; END;

INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'runtime_profile_revision',row.profile_id,json_array(row.revision,row.enabled),1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM runtime_profiles row;
CREATE TRIGGER attention_runtime_profiles_insert AFTER INSERT ON runtime_profiles BEGIN INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at) VALUES('runtime_profile_revision',NEW.profile_id,json_array(NEW.revision,NEW.enabled),1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(source_type,source_id) DO UPDATE SET state=excluded.state,episode=attention_operation_epochs.episode+1,first_detected_at=excluded.first_detected_at,last_changed_at=excluded.last_changed_at; END;
CREATE TRIGGER attention_runtime_profiles_state AFTER UPDATE OF revision,enabled ON runtime_profiles WHEN json_array(OLD.revision,OLD.enabled) IS NOT json_array(NEW.revision,NEW.enabled) BEGIN UPDATE attention_operation_epochs SET state=json_array(NEW.revision,NEW.enabled),episode=episode+1,first_detected_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),last_changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE source_type='runtime_profile_revision' AND source_id=NEW.profile_id; END;
CREATE TRIGGER attention_runtime_profiles_delete AFTER DELETE ON runtime_profiles BEGIN DELETE FROM attention_operation_epochs WHERE source_type='runtime_profile_revision' AND source_id=OLD.profile_id; END;

-- Explicit operator cleanup failures are metadata, never productive failure.
ALTER TABLE runtime_result_maintenance ADD COLUMN attention_failure_at TEXT;
ALTER TABLE runtime_result_maintenance ADD COLUMN attention_failure_code TEXT;
