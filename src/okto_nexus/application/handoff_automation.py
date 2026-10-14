"""Scoped internal authority for a broadcast candidate, rechecked before effects.

The durable binding records proof references, never an API key. HTTP/MCP
authentication does not accept this format. Possession of capacity grants no
authority here: current opt-in, identity, work grant and claim rules still apply.
"""
from dataclasses import asdict
import hashlib
import json

from nexus_connector_core.protocol import canonical_json

from ..domain.handoff_automation import HandoffAutomationPrincipal
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .runtime_policy import handoff_automation_guard

PREFIX = 'handoff-automation-v1:'


def denied():
    return OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Broadcast handoff automation is not authorized.', {})


def policy_digest(conn, agent_id):
    policy = handoff_automation_guard(conn, agent_id)
    if not policy['enabled'] or not policy['runtime']['runtime_enabled']:
        raise denied()
    return 'sha256:' + hashlib.sha256(canonical_json(policy)).hexdigest()


def binding(principal):
    return PREFIX + canonical_json(asdict(principal)).decode()


def context_for(principal):
    return RuntimeRequestContext(principal.agent_id, 'handoff_automation',
        represented_agent_id=principal.agent_id, workspace_id=principal.workspace_id,
        endpoint_id=principal.endpoint_id, execution_grant_id=principal.grant_id,
        request_id=principal.attempt_id, credential_binding=binding(principal),
        handoff_automation=principal)


def create_context(uow, *, access, agent_id, workspace_id, endpoint_id, handoff_id, grant_id, attempt_id):
    from .execution_binding_proposals import _agent_guard
    grants = access.grants.candidates(uow, actor_id=agent_id, endpoint_id=endpoint_id)
    grant = next((g for g in grants if g['grant_id'] == grant_id), None)
    if grant is None:
        raise denied()
    principal = HandoffAutomationPrincipal(agent_id, workspace_id, endpoint_id, handoff_id,
        attempt_id, grant_id, grant['revision'], policy_digest(uow.connection, agent_id),
        _agent_guard(uow.connection, agent_id))
    context = context_for(principal)
    access.authorize(context, action='execute_work', endpoint_id=endpoint_id,
        represented_agent_id=agent_id, workspace_id=workspace_id, uow=uow, audit=False)
    return context


def require_context(uow, context, *, action, endpoint_id, agent_id, workspace_id, handoff_id=None):
    from .execution_binding_proposals import _agent_guard
    p = context.handoff_automation
    if (type(p) is not HandoffAutomationPrincipal or context.authentication_source != 'handoff_automation'
            or context.trusted_local_operator or action != 'execute_work'
            or context.actor_agent_id != p.agent_id or context.represented_agent_id != p.agent_id
            or context.workspace_id != p.workspace_id or context.endpoint_id != p.endpoint_id
            or context.execution_grant_id != p.grant_id or context.request_id != p.attempt_id
            or context.credential_binding != binding(p)
            or (endpoint_id, agent_id, workspace_id) != (p.endpoint_id, p.agent_id, p.workspace_id)
            or handoff_id is not None and handoff_id != p.handoff_id):
        raise denied()
    if (p.policy_digest != policy_digest(uow.connection, p.agent_id)
            or p.agent_digest != _agent_guard(uow.connection, p.agent_id)):
        raise denied()
    handoff = uow.connection.execute('SELECT target,status,claimed_by FROM handoffs WHERE handoff_id=? AND workspace_id=?',
                                    (p.handoff_id, p.workspace_id)).fetchone()
    if (handoff is None or json.loads(handoff['target']).get('strategy') != 'broadcast'
            or handoff['status'] not in ('OPEN', 'CLAIMED')
            or handoff['status'] == 'CLAIMED' and handoff['claimed_by'] != p.agent_id):
        raise denied()
    return p


def restore_context(operation, work_binding):
    """Only durable managed work can restore this internal provenance."""
    try:
        raw = operation['credential_binding']
        principal = HandoffAutomationPrincipal(**json.loads(raw[len(PREFIX):]))
        if (not raw.startswith(PREFIX) or raw != binding(principal)
                or (operation['actor_agent_id'], operation['recipient_agent_id'], operation['workspace_id'],
                    operation['endpoint_id'], work_binding['handoff_id'], work_binding['grant_id'], work_binding['grant_revision'],
                    work_binding['idempotency_key'])
                != (principal.agent_id, principal.agent_id, principal.workspace_id, principal.endpoint_id,
                    principal.handoff_id, principal.grant_id, principal.grant_revision, principal.attempt_id)):
            raise denied()
        return context_for(principal)
    except (ValueError, TypeError, KeyError):
        raise denied() from None
