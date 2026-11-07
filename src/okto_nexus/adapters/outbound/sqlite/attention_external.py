"""Batched, read-only external attention facts with bounded retained history."""
from ....application.observations import ObservationService
from .observations_repo import CURRENT_FACTS_SQL, current_facts


_FIELDS = '''observed_instance_id source_id workspace_id external_instance_ref generation created_at updated_at
    agent_id source_kind registration_ref registration_hash revision enabled revoked_at source_created_at
    source_updated_at allowed_workspace_ids is_active api_key_hash deleted_at permissions head_generation
    source_revision publisher_token_id sequence report_hash received_at valid_until report_json
    last_completion_ref last_completion_received_at publisher_revoked_at'''.split()
_RAW = 'json_object(' + ','.join("'" + key + "',v." + key for key in _FIELDS) + ", 'continuity',c.last_received_at)"


def decode_facts(value):
    """Detach already-decoded SQL facts without a second JSON serialization.

    This is a pure adapter mapping inside the existing bounded callback. It
    performs no query, authentication, clock read or state mutation.
    """
    row = value['current']
    value['current'] = current_facts(row, source_last_received_at=row['continuity'])
    return value


def _expired(valid_until, received_at, observed_at, completion_received_at, now):
    # Reject corrupt temporal facts instead of silently filtering them away.
    # This small predicate avoids full JSON/source projection for ordinary
    # current working/idle/unknown heads and retains microsecond precision.
    return int(ObservationService._head_expired(dict(valid_until=valid_until,
        received_at=received_at, observed_at=observed_at,
        last_completion_received_at=completion_received_at), now))


SQL_FUNCTIONS = (('nexus_external_expired_v1', 5, _expired),)

SOURCE_SQL = """
WITH head_keys AS MATERIALIZED (
    SELECT h.observed_instance_id FROM observation_heads h
    JOIN observation_instances i USING(observed_instance_id)
    JOIN observation_sources s USING(source_id)
    LEFT JOIN observation_attention_anchors a USING(observed_instance_id)
    WHERE (:workspace_id IS NULL OR i.workspace_id=:workspace_id)
      AND (:agent_id IS NULL OR s.agent_id=:agent_id)
      AND ((:external_kind IS NULL OR :external_kind='external_blocked')
            AND h.state='blocked' AND a.blocked_sequence IS NOT NULL
        OR (:external_kind IS NULL OR :external_kind='external_observation_stale')
            AND nexus_external_expired_v1(h.valid_until,h.received_at,
                json_extract(h.report_json,'$.observed_at'),h.last_completion_received_at,:external_now))
), completions AS MATERIALIZED (
    SELECT e.event_id,e.payload,e.workspace_id,e.actor_agent_id,
        json_extract(e.payload,'$.observed_instance_id') AS observed_instance_id,
        json_extract(e.payload,'$.generation') AS generation,
        json_extract(e.payload,'$.sequence') AS sequence,
        json_extract(e.payload,'$.report_hash') AS report_hash,
        json_extract(e.payload,'$.source_revision') AS source_revision,
        json_extract(e.payload,'$.publisher_token_id') AS publisher_token_id
    FROM events e
    JOIN observation_instances i ON i.observed_instance_id=json_extract(e.payload,'$.observed_instance_id')
    JOIN observation_sources s USING(source_id)
    WHERE e.type='observation.completion'
      AND (:external_kind IS NULL OR :external_kind='external_completion_unseen')
      AND (:workspace_id IS NULL OR i.workspace_id=:workspace_id)
      AND (:agent_id IS NULL OR s.agent_id=:agent_id)
      AND e.workspace_id=i.workspace_id AND e.actor_agent_id=s.agent_id
      AND json_extract(e.payload,'$.source_id')=s.source_id
      AND json_extract(e.payload,'$.completion_ref') IS NOT NULL
      AND json_extract(e.payload,'$.completion_ref')<>''
), selected AS MATERIALIZED (""" + CURRENT_FACTS_SQL + """
    WHERE i.observed_instance_id IN (
        SELECT observed_instance_id FROM head_keys UNION SELECT observed_instance_id FROM completions)
), continuity AS MATERIALIZED (
    SELECT i.source_id,max(h.received_at) AS last_received_at
    FROM observation_instances i JOIN observation_heads h USING(observed_instance_id)
    WHERE i.source_id IN (SELECT DISTINCT source_id FROM selected) GROUP BY i.source_id
), facts AS MATERIALIZED (
    SELECT v.*,""" + _RAW + """ AS current_facts
    FROM selected v LEFT JOIN continuity c USING(source_id)
), completion_provenance AS MATERIALIZED (
    SELECT e.*,v.current_facts,v.source_id,
        COALESCE(e.source_revision,CASE WHEN e.generation=v.head_generation
            AND e.sequence=v.sequence AND e.report_hash=v.report_hash THEN v.source_revision END) AS proven_revision,
        COALESCE(e.publisher_token_id,CASE WHEN e.generation=v.head_generation
            AND e.sequence=v.sequence AND e.report_hash=v.report_hash THEN v.publisher_token_id END) AS proven_publisher,
        COALESCE(json_extract(e.payload,'$.observed_at'),CASE WHEN e.generation=v.head_generation
            AND e.sequence=v.sequence AND e.report_hash=v.report_hash
            THEN json_extract(v.report_json,'$.observed_at') END) AS observed_at
    FROM completions e JOIN facts v USING(observed_instance_id)
    WHERE e.workspace_id=v.workspace_id AND e.actor_agent_id=v.agent_id
      AND json_extract(e.payload,'$.source_id')=v.source_id
)
SELECT json_object('kind',:external_kind,'current',json(v.current_facts),'anchor',CASE WHEN a.observed_instance_id IS NOT NULL
    THEN json_object('generation',a.generation,'blocked_sequence',a.blocked_sequence,
        'blocked_started_at',a.blocked_started_at) END,'completion',NULL) AS facts
FROM facts v JOIN head_keys k USING(observed_instance_id)
LEFT JOIN observation_attention_anchors a USING(observed_instance_id)
UNION ALL
SELECT json_object('kind',:external_kind,'current',json(e.current_facts),'anchor',NULL,
    'completion',json_object('event_id',e.event_id,'report',json(e.payload),
        'source_revision',e.proven_revision,'observed_at',e.observed_at,
        'publisher_revoked',t.token_id IS NULL OR t.revoked_at IS NOT NULL)) AS facts
FROM completion_provenance e LEFT JOIN observation_tokens t ON t.token_id=e.proven_publisher
"""


def build_policy(uow, *, config, access, context, now):
    # The enclosing attention transaction already authenticates the operator.
    # No publisher capability grants access to this relation.
    return config
