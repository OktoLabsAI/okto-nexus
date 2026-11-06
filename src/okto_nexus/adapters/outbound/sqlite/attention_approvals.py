"""One metadata query for canonical approval review and retained history."""


SOURCE_SQL = """
WITH selected AS MATERIALIZED (
    SELECT a.*,CASE WHEN json_valid(a.request_payload) THEN a.request_payload ELSE '{}' END payload,
        CASE WHEN json_valid(a.request_payload) THEN
            json_type(a.request_payload)='object' AND json_type(a.request_payload,'$.kwargs')='object'
            ELSE 0 END AS payload_valid
    FROM approvals a
    WHERE (:workspace_id IS NULL OR a.workspace_id=:workspace_id)
      AND (:agent_id IS NULL OR a.agent_id=:agent_id)
      AND NOT EXISTS (SELECT 1 FROM execution_native_requests n WHERE n.canonical_request_id=a.approval_id)
), references_only AS MATERIALIZED (
    SELECT a.*,json_extract(payload,'$.kwargs.proposal_id') proposal_id,
        json_extract(payload,'$.kwargs.server_id') proposal_server,
        json_extract(payload,'$.kwargs.proposal_revision') proposal_revision,
        json_extract(payload,'$.kwargs.approved_diff_hash') approved_diff_hash
    FROM selected a
)
SELECT json_object(
    'approval_id',a.approval_id,'workspace_id',a.workspace_id,'agent_id',a.agent_id,
    'action',a.action,'status',a.status,'decision_revision',a.decision_revision,
    'created_at',a.created_at,'decided_at',a.decided_at,'archived_at',a.archived_at,
    'has_result',a.executed_result IS NOT NULL,'payload_valid',a.payload_valid,
    'recipient_type',json_type(a.payload,'$.kwargs.recipient_agent_id'),
    'recipient_agent_id',json_extract(a.payload,'$.kwargs.recipient_agent_id'),
    'has_coordination',json_type(a.payload,'$.kwargs._coordination') IS NOT NULL
        OR json_type(a.payload,'$.kwargs.client_request_id') IS NOT NULL,
    'coordination',CASE WHEN c.approval_id IS NOT NULL THEN json_object(
        'state',c.state,'resource_id',c.resource_id,'created_at',c.created_at,'expires_at',c.expires_at) END,
    'coordination_matches',json_type(a.payload,'$.kwargs._coordination')='object'
        AND json_extract(a.payload,'$.kwargs._coordination.revision')=1
        AND json_extract(a.payload,'$.kwargs._coordination.approval_id')=a.approval_id
        AND c.server_id=i.server_id
        AND c.actor_agent_id=a.agent_id AND c.workspace_id=a.workspace_id
        AND c.operation=CASE WHEN a.action='handoff_create' THEN 'handoff_create' ELSE 'message_create' END
        AND c.client_request_id=json_extract(a.payload,'$.kwargs.client_request_id')
        AND c.server_id=json_extract(a.payload,'$.kwargs._coordination.server_id')
        AND c.actor_agent_id=json_extract(a.payload,'$.kwargs._coordination.actor_agent_id')
        AND c.workspace_id=json_extract(a.payload,'$.kwargs._coordination.workspace_id')
        AND c.operation=json_extract(a.payload,'$.kwargs._coordination.operation')
        AND c.client_request_id=json_extract(a.payload,'$.kwargs._coordination.client_request_id')
        AND c.request_hash=json_extract(a.payload,'$.kwargs._coordination.request_hash'),
    'proposal',CASE WHEN p.proposal_id IS NOT NULL THEN json_object(
        'status',p.status,'expires_at',p.expires_at,'proposal_revision',p.proposal_revision) END,
    'proposal_matches',p.subject_agent_id=a.agent_id
        AND json_extract(p.expected_revisions_json,'$.operator_approval_id')=a.approval_id
        AND p.diff_hash=a.approved_diff_hash AND p.proposal_revision=a.proposal_revision
        AND json_extract(p.proposal_json,'$.workspace_id')=a.workspace_id,
    'legacy',CASE WHEN l.approval_id IS NOT NULL THEN json_object(
        'state',l.state,'expires_at',l.expires_at) END,
    'orphan_native_expires_at',CASE WHEN a.action='execution.native.respond'
        THEN json_extract(a.payload,'$.kwargs.expires_at') END,
    'source_revision',json_array(c.server_id,c.actor_agent_id,c.workspace_id,c.operation,
        c.client_request_id,c.state,c.created_at,c.expires_at,p.proposal_revision,p.status,
        p.expires_at,l.state,l.expires_at)
) AS facts
FROM references_only a
LEFT JOIN execution_installation i ON i.singleton=1
LEFT JOIN coordination_requests c ON c.server_id=i.server_id AND c.approval_id=a.approval_id
LEFT JOIN execution_proposals p ON a.action='execution.binding.authorize'
    AND p.proposal_id=a.proposal_id AND p.server_id=a.proposal_server AND p.subject_agent_id=a.agent_id
LEFT JOIN runtime_native_approvals l ON a.action='runtime_native_approval' AND l.approval_id=a.approval_id
"""


def build_policy(uow, *, config, access, context, now, decision_registry=None):
    """Consume the process registry snapshot once; never call its handlers."""
    return dict(viewer_is_operator=access.authenticate(context, uow=uow, require_feature=False),
        viewer_actor=context.actor_agent_id or 'operator',
        decision_registry={action: {key: modes.get(key) is True for key in ('executor', 'validator', 'transactional')}
            for action, modes in (decision_registry or {}).items()})
