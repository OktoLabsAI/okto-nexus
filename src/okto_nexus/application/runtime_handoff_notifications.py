"""Durable metadata notifications, separate from governed handoff execution."""
from dataclasses import asdict
import json
from types import SimpleNamespace

from ..domain.routing import RoutingAgent, can_agent_see_event, is_agent_eligible
from ..domain.runtime_context import RuntimeRequestContext
from ..domain.tag_selector import reachable
from ..errors import ErrorCode, OktoNexusError
from .execution_binding_proposals import _agent_guard
from .permissions import permission_set_for
from .runtime_policy import effective

PREFIX = 'handoff-notification-v1:'


def has_runtime(uow, agent_id, workspace_id):
    return effective(uow.connection, agent_id)['runtime_enabled'] and uow.connection.execute(
        "SELECT 1 FROM agent_endpoints WHERE agent_id=? AND workspace_id=? AND enabled=1 "
        "AND activation_state='approved' AND consumption='exclusive' AND response_policy='conversation' LIMIT 1",
        (agent_id, workspace_id)).fetchone() is not None


def eligible(uow, *, agents, handoff, recipient_id, now, governance=None):
    sender = agents.get(uow, handoff.from_agent_id)
    recipient = agents.get(uow, recipient_id)
    if (not sender or not sender.is_active or not recipient or not recipient.is_active
            or recipient_id == sender.agent_id or not reachable(sender, recipient)):
        return False
    view = RoutingAgent(agent_id=recipient_id, workspace_id=handoff.workspace_id,
        role=recipient.role, capabilities=recipient.capabilities, tags=recipient.tags)
    try:
        permission_set_for(agents, uow, sender.agent_id).require('handoffs', 'create')
        permission_set_for(agents, uow, recipient_id).require('handoffs', 'work')
        if governance and not governance.audience_reachable(uow,
                sender_id=sender.agent_id, sender_tags=sender.tags,
                recipient_id=recipient_id, recipient_tags=recipient.tags):
            return False
        return (can_agent_see_event(view, handoff, now)
                and is_agent_eligible(view, handoff.target, handoff.created_at, now))
    except OktoNexusError:
        return False


def queue(uow, *, message, delivery, agents, handoffs, now, governance=None):
    body = json.loads(message.body)
    kind = body.get('kind')
    if kind not in {'handoff.directed', 'handoff.created', 'handoff.unblocked'}:
        return
    handoff = handoffs.get(uow, workspace_id=message.workspace_id, handoff_id=body['handoff_id'])
    if (not handoff
            or not has_runtime(uow, delivery.recipient_agent_id, message.workspace_id)
            or not eligible(uow, agents=agents, handoff=handoff, recipient_id=delivery.recipient_agent_id, now=now, governance=governance)):
        return
    event = 'handoff.created' if kind == 'handoff.directed' else kind
    uow.connection.execute('INSERT INTO runtime_handoff_notifications VALUES(?,?,?,?,?)',
        (message.message_id, handoff.handoff_id, delivery.recipient_agent_id, event,
         _agent_guard(uow.connection, message.from_agent_id)))
    context = RuntimeRequestContext(message.from_agent_id, 'handoff_notification',
                                    credential_binding=PREFIX + message.message_id)
    uow.connection.execute('INSERT INTO runtime_pending_deliveries(delivery_id,context_json,authorization_revision,created_at) VALUES(?,?,?,?)',
        (delivery.delivery_id, json.dumps(asdict(context)), 'handoff-notification', now))


def valid_binding(uow, actor, binding, workspace_id):
    row = uow.connection.execute(
        'SELECT n.actor_guard,m.from_agent_id,m.workspace_id FROM runtime_handoff_notifications n '
        'JOIN messages m USING(message_id) WHERE n.message_id=?', (binding[len(PREFIX):],)).fetchone()
    return bool(row and row['from_agent_id'] == actor.agent_id and row['workspace_id'] == workspace_id
                and row['actor_guard'] == _agent_guard(uow.connection, actor.agent_id))


def validate(uow, *, message, recipient_id, agents, now, governance=None):
    row = uow.connection.execute('SELECT * FROM runtime_handoff_notifications WHERE message_id=? AND recipient_agent_id=?',
                                 (message.message_id, recipient_id)).fetchone()
    record = uow.connection.execute('SELECT * FROM handoffs WHERE handoff_id=? AND workspace_id=?',
        (row['handoff_id'], message.workspace_id)).fetchone() if row else None
    handoff = SimpleNamespace(**dict(record)) if record else None
    if (not handoff or handoff.status != 'OPEN' or not eligible(uow, agents=agents, handoff=handoff,
                                                              recipient_id=recipient_id, now=now, governance=governance)):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Handoff notification is no longer available to this recipient.', {})
