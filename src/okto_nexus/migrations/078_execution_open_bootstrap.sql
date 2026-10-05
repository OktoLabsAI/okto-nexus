-- A bootstrap send is fenced without pretending a lease has been installed.
ALTER TABLE execution_dispatch_outbox ADD COLUMN dispatch_phase TEXT
    CHECK (dispatch_phase IN ('OPEN_AUTHORIZED_PENDING_LEASE','LEASE_AUTHORIZED'));
ALTER TABLE execution_dispatch_outbox ADD COLUMN dispatch_grant_id TEXT;
ALTER TABLE execution_dispatch_outbox ADD COLUMN dispatch_connection_id TEXT;
