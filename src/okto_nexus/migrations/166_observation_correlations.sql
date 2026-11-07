-- Explicit observational selection, never execution authority.
-- No FK: canonical/OBS retirement must not erase the revision tombstone.
CREATE TABLE observation_correlations (
    observed_instance_id TEXT PRIMARY KEY NOT NULL
        CHECK(length(observed_instance_id) BETWEEN 1 AND 160
          AND substr(observed_instance_id,1,1) GLOB '[A-Za-z0-9]'
          AND observed_instance_id NOT GLOB '*[^A-Za-z0-9._:-]*'),
    agent_id TEXT NOT NULL CHECK(length(agent_id) BETWEEN 1 AND 160),
    workspace_id TEXT NOT NULL CHECK(length(workspace_id) BETWEEN 1 AND 160),
    schema_version INTEGER NOT NULL CHECK(typeof(schema_version)='integer' AND schema_version=1),
    revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>0),
    state TEXT NOT NULL CHECK(state IN ('selected','cleared','revoked')),
    server_id TEXT,
    executor_id TEXT,
    session_id TEXT,
    selection_json TEXT CHECK(selection_json IS NULL OR
        (json_valid(selection_json) AND json_type(selection_json)='object'
         AND length(CAST(selection_json AS BLOB))<=8192)),
    proof_json TEXT CHECK(proof_json IS NULL OR
        (json_valid(proof_json) AND json_type(proof_json)='object'
         AND length(CAST(proof_json AS BLOB))<=2048)),
    correlation_digest TEXT CHECK(correlation_digest IS NULL OR
        (length(correlation_digest)=71 AND substr(correlation_digest,1,7)='sha256:'
         AND substr(correlation_digest,8) NOT GLOB '*[^0-9a-f]*')),
    verified_at TEXT,
    updated_at TEXT NOT NULL,
    CHECK((state='selected' AND server_id IS NOT NULL AND executor_id IS NOT NULL
        AND session_id IS NOT NULL AND selection_json IS NOT NULL AND proof_json IS NOT NULL
        AND correlation_digest IS NOT NULL AND verified_at IS NOT NULL
        AND json_extract(selection_json,'$.observed_instance_id') IS observed_instance_id
        AND json_extract(selection_json,'$.server_id') IS server_id
        AND json_extract(selection_json,'$.executor_id') IS executor_id
        AND json_extract(selection_json,'$.session_id') IS session_id
        AND json_extract(selection_json,'$.expected_correlation_revision') IS revision-1)
      OR (state IN ('cleared','revoked') AND server_id IS NULL AND executor_id IS NULL
        AND session_id IS NULL AND selection_json IS NULL AND proof_json IS NULL
        AND correlation_digest IS NULL AND verified_at IS NULL))
);
CREATE INDEX observation_correlations_session
ON observation_correlations(server_id,executor_id,session_id,observed_instance_id)
WHERE state='selected';
