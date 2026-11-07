-- External telemetry has its own credentials and never creates canonical work.
-- The allocator has no FK: both reset modes preserve its high-water mark.
CREATE TABLE observation_installation (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    last_generation INTEGER NOT NULL CHECK(typeof(last_generation)='integer' AND last_generation>=0)
);
INSERT INTO observation_installation VALUES(1,0);

CREATE TABLE observation_sources (
    source_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE RESTRICT,
    source_kind TEXT NOT NULL CHECK(source_kind IN ('herdr','hook','custom')),
    registration_ref TEXT NOT NULL CHECK(length(registration_ref) BETWEEN 1 AND 256),
    registration_hash TEXT NOT NULL CHECK(length(registration_hash)=64),
    revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>0),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(agent_id,registration_ref)
);
CREATE INDEX observation_sources_agent ON observation_sources(agent_id,source_id);

CREATE TABLE observation_source_workspaces (
    source_id TEXT NOT NULL REFERENCES observation_sources(source_id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
    PRIMARY KEY(source_id,workspace_id)
);
CREATE INDEX observation_workspaces_scope ON observation_source_workspaces(workspace_id,source_id);

CREATE TABLE observation_instances (
    observed_instance_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES observation_sources(source_id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
    external_instance_ref TEXT NOT NULL CHECK(length(external_instance_ref) BETWEEN 1 AND 256),
    generation INTEGER NOT NULL CHECK(typeof(generation)='integer' AND generation>0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_id,workspace_id,external_instance_ref)
);
CREATE INDEX observation_instances_source ON observation_instances(source_id,observed_instance_id);
CREATE INDEX observation_instances_workspace ON observation_instances(workspace_id,observed_instance_id);

CREATE TABLE observation_tokens (
    token_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE CHECK(length(token_hash)=64 AND token_hash NOT GLOB '*[^0-9a-f]*'),
    audience TEXT NOT NULL CHECK(audience='observations.publish'),
    source_id TEXT NOT NULL REFERENCES observation_sources(source_id) ON DELETE CASCADE,
    source_revision INTEGER NOT NULL CHECK(typeof(source_revision)='integer' AND source_revision>0),
    issuer_agent_id TEXT REFERENCES agents(agent_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX observation_tokens_source ON observation_tokens(source_id,expires_at,token_id);
CREATE INDEX observation_tokens_issuer ON observation_tokens(issuer_agent_id,token_id);
CREATE INDEX observation_tokens_expiry ON observation_tokens(expires_at,token_id);
CREATE INDEX observation_tokens_revoked ON observation_tokens(revoked_at,token_id) WHERE revoked_at IS NOT NULL;

CREATE TABLE observation_token_instances (
    token_id TEXT NOT NULL REFERENCES observation_tokens(token_id) ON DELETE CASCADE,
    observed_instance_id TEXT NOT NULL REFERENCES observation_instances(observed_instance_id) ON DELETE CASCADE,
    generation INTEGER NOT NULL CHECK(typeof(generation)='integer' AND generation>0),
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
    PRIMARY KEY(token_id,observed_instance_id)
);
CREATE INDEX observation_grants_instance ON observation_token_instances(observed_instance_id,token_id);

CREATE TABLE observation_heads (
    observed_instance_id TEXT PRIMARY KEY REFERENCES observation_instances(observed_instance_id) ON DELETE CASCADE,
    generation INTEGER NOT NULL CHECK(typeof(generation)='integer' AND generation>0),
    source_revision INTEGER NOT NULL CHECK(typeof(source_revision)='integer' AND source_revision>0),
    publisher_token_id TEXT NOT NULL REFERENCES observation_tokens(token_id) ON DELETE RESTRICT,
    sequence INTEGER NOT NULL CHECK(typeof(sequence)='integer' AND sequence>0),
    report_hash TEXT NOT NULL CHECK(length(report_hash)=71 AND substr(report_hash,1,7)='sha256:' AND substr(report_hash,8) NOT GLOB '*[^0-9a-f]*'),
    state TEXT NOT NULL CHECK(state IN ('working','idle','blocked','unknown')),
    evidence TEXT NOT NULL CHECK(evidence IN ('reported','inferred')),
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    report_json TEXT NOT NULL CHECK(json_valid(report_json) AND length(CAST(report_json AS BLOB))<=4096),
    last_completion_ref TEXT CHECK(last_completion_ref IS NULL OR length(last_completion_ref) BETWEEN 1 AND 256),
    last_completion_received_at TEXT
);
CREATE INDEX observation_heads_publisher ON observation_heads(publisher_token_id,observed_instance_id);
CREATE INDEX observation_heads_validity ON observation_heads(valid_until,observed_instance_id);

-- Fixed-point credits survive restart/reset for retained sources and agents.
-- Installation is never pruned. Only removed entity buckets are obsolete;
-- full_at calculated under old rate policy cannot authorize a fresh burst.
CREATE TABLE observation_rate_buckets (
    scope_kind TEXT NOT NULL CHECK(scope_kind IN ('source','agent','installation')),
    scope_id TEXT NOT NULL,
    balance INTEGER NOT NULL CHECK(typeof(balance)='integer' AND balance>=0),
    last_refill_us INTEGER NOT NULL CHECK(typeof(last_refill_us)='integer'),
    full_at_us INTEGER NOT NULL CHECK(typeof(full_at_us)='integer'),
    PRIMARY KEY(scope_kind,scope_id)
);
CREATE INDEX observation_buckets_full ON observation_rate_buckets(full_at_us,scope_kind,scope_id);
CREATE INDEX observation_events_retention ON events(created_at,event_id) WHERE type GLOB 'observation.*';
CREATE INDEX observation_events_sequence ON events(event_id) WHERE type GLOB 'observation.*';

-- Snapshot permissions are materialized on agents. Preset IDs are descriptive.
-- json_valid + json_type='true' deliberately deny absent, null, numeric/string
-- truthiness and malformed permissions without failing the identity UPDATE.
CREATE TRIGGER observation_agent_authority_changed AFTER UPDATE OF is_active,api_key_hash,deleted_at,permissions ON agents
WHEN OLD.is_active IS NOT NEW.is_active OR OLD.api_key_hash IS NOT NEW.api_key_hash OR OLD.deleted_at IS NOT NEW.deleted_at
 OR (CASE WHEN json_valid(OLD.permissions) THEN COALESCE(json_type(OLD.permissions,'$.observations.manage_self')='true',0) ELSE 0 END) IS NOT (CASE WHEN json_valid(NEW.permissions) THEN COALESCE(json_type(NEW.permissions,'$.observations.manage_self')='true',0) ELSE 0 END)
 OR (CASE WHEN json_valid(OLD.permissions) THEN COALESCE(json_type(OLD.permissions,'$.observations.publish')='true',0) ELSE 0 END) IS NOT (CASE WHEN json_valid(NEW.permissions) THEN COALESCE(json_type(NEW.permissions,'$.observations.publish')='true',0) ELSE 0 END)
BEGIN
    UPDATE observation_tokens SET revoked_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE revoked_at IS NULL AND (issuer_agent_id=NEW.agent_id OR source_id IN (SELECT source_id FROM observation_sources WHERE agent_id=NEW.agent_id));
END;

CREATE TRIGGER observation_source_authority_changed AFTER UPDATE OF revision,enabled,revoked_at ON observation_sources
WHEN OLD.revision IS NOT NEW.revision OR OLD.enabled IS NOT NEW.enabled OR OLD.revoked_at IS NOT NEW.revoked_at
BEGIN
    UPDATE observation_tokens SET revoked_at=COALESCE(NEW.revoked_at,NEW.updated_at)
    WHERE source_id=NEW.source_id AND revoked_at IS NULL;
END;

CREATE TRIGGER observation_instance_generation_changed AFTER UPDATE OF generation ON observation_instances
WHEN OLD.generation IS NOT NEW.generation
BEGIN
    UPDATE observation_tokens SET revoked_at=NEW.updated_at WHERE revoked_at IS NULL
    AND token_id IN (SELECT token_id FROM observation_token_instances WHERE observed_instance_id=NEW.observed_instance_id);
END;
