-- A lane is a binding-scoped, generation-fenced control admission.
CREATE TABLE execution_control_lanes (
    server_id TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    binding_id TEXT NOT NULL,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    ticket_id TEXT NOT NULL REFERENCES execution_link_tickets(ticket_id),
    attach_request_id TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    connection_generation INTEGER NOT NULL CHECK (connection_generation >= 1),
    credential_epoch INTEGER NOT NULL CHECK (credential_epoch >= 1),
    authorization_revision INTEGER NOT NULL CHECK (authorization_revision >= 1),
    configuration_revision INTEGER NOT NULL CHECK (configuration_revision >= 1),
    expires_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('ADMITTED','DISCONNECTED')),
    PRIMARY KEY (server_id,executor_id,binding_id),
    FOREIGN KEY (server_id,executor_id,binding_id)
        REFERENCES execution_bindings(server_id,executor_id,binding_id)
);
CREATE INDEX idx_execution_control_lanes_connection
    ON execution_control_lanes(server_id,executor_id,connection_id,connection_generation);
CREATE TRIGGER execution_ticket_revoke_lane
AFTER UPDATE OF revoked_at ON execution_link_tickets
WHEN NEW.revoked_at IS NOT NULL
BEGIN
    UPDATE execution_control_lanes SET state='DISCONNECTED'
    WHERE ticket_id=NEW.ticket_id;
END;
CREATE TRIGGER execution_agent_revision_close_lanes
AFTER UPDATE OF credential_epoch,authorization_revision,configuration_revision
ON execution_agent_revisions
WHEN NEW.credential_epoch<>OLD.credential_epoch
    OR NEW.authorization_revision<>OLD.authorization_revision
    OR NEW.configuration_revision<>OLD.configuration_revision
BEGIN
    UPDATE execution_control_lanes SET state='DISCONNECTED'
    WHERE server_id=NEW.server_id AND agent_id=NEW.agent_id;
END;
