"""One result episode per canonical handoff claim, or independent native turn.

The write-time timestamp anchor survives partial result retention. It contains
no output, authority or decision and disappears with the source handoff.
"""


_LINKS = """
SELECT r.server_id,r.executor_id,r.operation_id,r.session_id,r.stream_epoch,
       r.terminal_sequence,r.delivery_outcome,r.captured_at,
       p.workspace_id,p.subject_agent_id AS agent_id,b.handoff_id,b.claim_epoch
FROM execution_results r JOIN execution_operations p USING(server_id,executor_id,operation_id)
JOIN execution_domain_deliveries m USING(server_id,executor_id,operation_id)
JOIN delivery_outbox d ON d.operation_id=m.domain_operation_id
JOIN runtime_handoff_bindings b ON b.operation_id=d.operation_id
JOIN handoffs h ON h.handoff_id=b.handoff_id
WHERE r.terminal_sequence IS NOT NULL AND r.delivery_outcome IN ('success','failed','interrupted')
  AND p.action IN ('turn.submit','turn.steer')
  AND p.workspace_id=d.workspace_id AND h.workspace_id=d.workspace_id
  AND p.subject_agent_id=d.recipient_agent_id
  AND (h.claim_epoch<>b.claim_epoch OR h.claimed_by=d.recipient_agent_id)
"""


def _anchor(select):
    return """
INSERT INTO attention_operation_epochs(source_type,source_id,state,episode,first_detected_at,last_changed_at)
SELECT 'handoff_result',json_array(handoff_id,claim_epoch),'result',1,recorded_at,recorded_at
FROM (""" + select + """) WHERE 1
ON CONFLICT(source_type,source_id) DO UPDATE SET
first_detected_at=CASE WHEN julianday(excluded.first_detected_at)<julianday(attention_operation_epochs.first_detected_at)
    THEN excluded.first_detected_at ELSE attention_operation_epochs.first_detected_at END,
last_changed_at=CASE WHEN julianday(excluded.last_changed_at)>julianday(attention_operation_epochs.last_changed_at)
    THEN excluded.last_changed_at ELSE attention_operation_epochs.last_changed_at END;
"""


# updated_at is optional in the canonical handoff schema, including terminal
# imports. Preserve its known timestamp or fall back to the stored creation.
_HANDOFF = "SELECT handoff_id,claim_epoch,COALESCE(updated_at,created_at) AS recorded_at FROM handoffs WHERE status IN ('COMPLETED','REJECTED')"
_EXECUTION = 'SELECT handoff_id,claim_epoch,captured_at AS recorded_at FROM (' + _LINKS + ')'
_NEW_EXECUTION = _EXECUTION + ' WHERE server_id=NEW.server_id AND executor_id=NEW.executor_id AND operation_id=NEW.operation_id'

# Release 161 used independent native-turn identities even for managed handoff
# work. Preserve their viewing preferences when the productive claim becomes
# the shared identity. Keep old rows for historical references and rollback.
_PREFERENCE_BACKFILL = """
WITH aliases AS MATERIALIZED (
    SELECT DISTINCT
        nexus_attention_id_v1('result_unseen','execution_result',operation_id,
            json_array(server_id,executor_id,stream_epoch,terminal_sequence)) AS old_id,
        nexus_attention_id_v1('result_unseen','handoff_result',handoff_id,json(claim_epoch)) AS new_id
    FROM (""" + _LINKS + """)
), legacy AS MATERIALIZED (
    SELECT p.*,a.new_id FROM aliases a JOIN attention_preferences p ON p.attention_id=a.old_id
), candidates AS MATERIALIZED (
    SELECT * FROM legacy UNION ALL
    SELECT p.*,p.attention_id AS new_id FROM attention_preferences p
    WHERE EXISTS(SELECT 1 FROM legacy l WHERE l.principal=p.principal AND l.new_id=p.attention_id)
), merged AS (
    SELECT principal,new_id,
        FIRST_VALUE(seen_at) OVER (PARTITION BY principal,new_id
            ORDER BY seen_at IS NULL,nexus_attention_stamp_v1(seen_at),seen_at) AS seen_at,
        FIRST_VALUE(snoozed_until) OVER (PARTITION BY principal,new_id
            ORDER BY nexus_attention_stamp_v1(snoozed_until) DESC,snoozed_until DESC) AS snoozed_until,
        FIRST_VALUE(updated_at) OVER (PARTITION BY principal,new_id
            ORDER BY nexus_attention_stamp_v1(updated_at) DESC,updated_at DESC) AS updated_at,
        MAX(revision) OVER (PARTITION BY principal,new_id)+1 AS revision,
        ROW_NUMBER() OVER (PARTITION BY principal,new_id ORDER BY attention_id) AS ordinal
    FROM candidates
)
INSERT INTO attention_preferences(principal,attention_id,seen_at,snoozed_until,revision,updated_at)
SELECT principal,new_id,seen_at,snoozed_until,revision,updated_at FROM merged WHERE ordinal=1
ON CONFLICT(principal,attention_id) DO UPDATE SET seen_at=excluded.seen_at,
    snoozed_until=excluded.snoozed_until,revision=excluded.revision,updated_at=excluded.updated_at;
"""

# Migration 162 includes this exact block. Existing canonical timestamps are
# known facts; no read time or reconstructed historical transition is invented.
RESULT_ANCHOR_SQL = _anchor(_HANDOFF) + _anchor(_EXECUTION) + """
CREATE TRIGGER attention_handoff_result_insert AFTER INSERT ON handoffs
WHEN NEW.status IN ('COMPLETED','REJECTED') BEGIN
""" + _anchor(_HANDOFF + ' AND handoff_id=NEW.handoff_id') + """END;
CREATE TRIGGER attention_handoff_result_terminal AFTER UPDATE OF status,claim_epoch ON handoffs
WHEN NEW.status IN ('COMPLETED','REJECTED') AND (OLD.status IS NOT NEW.status OR OLD.claim_epoch IS NOT NEW.claim_epoch) BEGIN
""" + _anchor(_HANDOFF + ' AND handoff_id=NEW.handoff_id') + """END;
CREATE TRIGGER attention_execution_result_insert AFTER INSERT ON execution_results
WHEN NEW.terminal_sequence IS NOT NULL BEGIN
""" + _anchor(_NEW_EXECUTION) + """END;
CREATE TRIGGER attention_execution_result_terminal AFTER UPDATE OF terminal_sequence,delivery_outcome ON execution_results
WHEN NEW.terminal_sequence IS NOT NULL AND (OLD.terminal_sequence IS NOT NEW.terminal_sequence OR OLD.delivery_outcome IS NOT NEW.delivery_outcome) BEGIN
""" + _anchor(_NEW_EXECUTION) + """END;
CREATE TRIGGER attention_handoff_result_delete AFTER DELETE ON handoffs BEGIN
DELETE FROM attention_operation_epochs WHERE source_type='handoff_result' AND json_extract(source_id,'$[0]')=OLD.handoff_id;
END;
""" + _PREFERENCE_BACKFILL


SOURCE_SQL = """
WITH linked_native AS MATERIALIZED (""" + _LINKS + """
  AND (:workspace_id IS NULL OR p.workspace_id=:workspace_id)
  AND (:agent_id IS NULL OR p.subject_agent_id=:agent_id)
), ordered_native AS MATERIALIZED (
    SELECT * FROM linked_native ORDER BY handoff_id,claim_epoch,server_id,executor_id,operation_id
), native_groups AS MATERIALIZED (
    SELECT handoff_id,claim_epoch,json_group_array(json_object(
        'server_id',server_id,'executor_id',executor_id,'operation_id',operation_id,
        'session_id',session_id,'stream_epoch',stream_epoch,'terminal_sequence',terminal_sequence,
        'delivery_outcome',delivery_outcome,'captured_at',captured_at,'agent_id',agent_id)) AS native_results
    FROM ordered_native GROUP BY handoff_id,claim_epoch
), terminal_handoffs AS MATERIALIZED (
    SELECT h.*,COALESCE(h.claimed_by,
        CASE WHEN json_extract(h.target,'$.strategy') IN ('direct','direct_with_fallback')
             THEN json_extract(h.target,'$.agent_id') END,h.from_agent_id) AS result_agent_id
    FROM handoffs h WHERE h.status IN ('COMPLETED','REJECTED')
      AND (:workspace_id IS NULL OR h.workspace_id=:workspace_id)
      AND (:agent_id IS NULL OR COALESCE(h.claimed_by,
        CASE WHEN json_extract(h.target,'$.strategy') IN ('direct','direct_with_fallback')
             THEN json_extract(h.target,'$.agent_id') END,h.from_agent_id)=:agent_id)
), episodes AS (
    SELECT handoff_id,claim_epoch FROM native_groups UNION SELECT handoff_id,claim_epoch FROM terminal_handoffs
)
SELECT json_object('source_type','handoff_result','handoff_id',k.handoff_id,'claim_epoch',k.claim_epoch,
    'workspace_id',h.workspace_id,'agent_id',t.result_agent_id,
    'terminal_status',t.status,'terminal_at',COALESCE(t.updated_at,t.created_at),
    'native_results',json(COALESCE(n.native_results,'[]')),
    'first_detected_at',a.first_detected_at,'last_changed_at',a.last_changed_at) AS facts
FROM episodes k JOIN handoffs h ON h.handoff_id=k.handoff_id
LEFT JOIN terminal_handoffs t ON t.handoff_id=k.handoff_id AND t.claim_epoch=k.claim_epoch
LEFT JOIN native_groups n ON n.handoff_id=k.handoff_id AND n.claim_epoch=k.claim_epoch
JOIN attention_operation_epochs a ON a.source_type='handoff_result' AND a.source_id=json_array(k.handoff_id,k.claim_epoch)
UNION ALL
SELECT json_object('source_type','execution_result','server_id',r.server_id,'executor_id',r.executor_id,
    'operation_id',r.operation_id,'session_id',r.session_id,'stream_epoch',r.stream_epoch,
    'terminal_sequence',r.terminal_sequence,'delivery_outcome',r.delivery_outcome,'captured_at',r.captured_at,
    'workspace_id',p.workspace_id,'agent_id',p.subject_agent_id)
FROM execution_results r JOIN execution_operations p USING(server_id,executor_id,operation_id)
WHERE r.terminal_sequence IS NOT NULL AND r.delivery_outcome IN ('success','failed','interrupted')
  AND (:workspace_id IS NULL OR p.workspace_id=:workspace_id)
  AND (:agent_id IS NULL OR p.subject_agent_id=:agent_id)
  AND NOT EXISTS(SELECT 1 FROM linked_native n
    WHERE n.server_id=r.server_id AND n.executor_id=r.executor_id AND n.operation_id=r.operation_id)
"""


def build_policy(uow, *, config, access, context, now):
    # AttentionService already authenticates the operator in the same read UoW.
    # Result inspection is navigation; the canonical read checks its own access.
    return {}
