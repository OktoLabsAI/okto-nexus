"""Durable metadata notifications, separate from governed handoff execution."""
from dataclasses import asdict
import json
from types import SimpleNamespace
from typing import Protocol

from ..domain.routing import RoutingAgent, can_agent_see_event, is_agent_eligible
from ..domain.runtime_context import RuntimeRequestContext
from ..domain.tag_selector import reachable
from ..errors import ErrorCode, OktoNexusError
from .execution_binding_proposals import _agent_guard
from .permissions import permission_set_for
from .runtime_policy import effective

PREFIX = 'handoff-notification-v1:'
# Lifecycle notices go to the creator or to the previous claimant. They stay
# valid after the handoff leaves OPEN.
OUTCOME_KINDS = frozenset({'handoff.completed', 'handoff.rejected', 'handoff.cancelled',
    'handoff.lease_expired', 'handoff.claimant_silent', 'handoff.claimant_contained'})


class HandoffNotificationRepository(Protocol):
    def record(self, uow, *, message_id, handoff_id, recipient_id, event_type, actor_guard, competitive): ...
    def competitive(self, uow, *, message_id, recipient_id) -> bool: ...


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


def queue(uow, *, message, delivery, agents, handoffs, now, governance=None,
          notifications: HandoffNotificationRepository | None = None, runtime_enabled=True):
    body = json.loads(message.body)
    kind = body.get('kind')
    if kind in OUTCOME_KINDS:
        queue_outcome(uow, message=message, delivery=delivery, handoff_id=body.get('handoff_id'), kind=kind,
            agents=agents, handoffs=handoffs, now=now, notifications=notifications, runtime_enabled=runtime_enabled)
        return
    if kind not in {'handoff.directed', 'handoff.created', 'handoff.unblocked'}:
        return
    handoff = handoffs.get(uow, workspace_id=message.workspace_id, handoff_id=body['handoff_id'])
    competitive = bool(handoff and json.loads(handoff.target).get('strategy') == 'broadcast')
    if (not handoff
            or not competitive and (not runtime_enabled or not has_runtime(uow, delivery.recipient_agent_id, message.workspace_id))
            or not eligible(uow, agents=agents, handoff=handoff, recipient_id=delivery.recipient_agent_id, now=now, governance=governance)):
        return
    event = 'handoff.created' if kind == 'handoff.directed' else kind
    if notifications is None:
        raise RuntimeError('Handoff notification persistence is not configured.')
    notifications.record(uow, message_id=message.message_id, handoff_id=handoff.handoff_id,
        recipient_id=delivery.recipient_agent_id, event_type=event,
        actor_guard=_agent_guard(uow.connection, message.from_agent_id), competitive=competitive)
    if competitive:
        return  # Logical inbox remains unread; no conversational producer exists.
    context = RuntimeRequestContext(message.from_agent_id, 'handoff_notification',
                                    credential_binding=PREFIX + message.message_id)
    uow.connection.execute('INSERT INTO runtime_pending_deliveries(delivery_id,context_json,authorization_revision,created_at) VALUES(?,?,?,?)',
        (delivery.delivery_id, json.dumps(asdict(context)), 'handoff-notification', now))


def _participants(handoff, message):
    """Return the agents that may receive a lifecycle notice of this handoff."""
    try:
        previous = json.loads(message.body).get('previous_claimed_by')
    except (TypeError, ValueError, AttributeError):
        previous = None
    return {a for a in (handoff.from_agent_id, handoff.claimed_by, previous) if a}


def queue_outcome(uow, *, message, delivery, handoff_id, kind, agents, handoffs, now,
                  notifications: HandoffNotificationRepository | None = None, runtime_enabled=True):
    """Push one lifecycle notice to a recipient that has a runtime session.

    The message and the delivery exist already. The function returns True when
    it queues a runtime turn. It returns False and leaves the inbox message when
    the recipient has no runtime, is not the creator or a claimant of the
    handoff, or already got this kind for this claim epoch. WP4 calls this
    function for ``handoff.lease_expired`` and ``handoff.claimant_silent``.
    The body of the message may name ``previous_claimed_by``.
    """
    if kind not in OUTCOME_KINDS:
        raise ValueError(f'Unknown handoff notice kind: {kind}')
    handoff = handoffs.get(uow, workspace_id=message.workspace_id, handoff_id=handoff_id) if handoff_id else None
    recipient_id = delivery.recipient_agent_id
    if not handoff or recipient_id not in _participants(handoff, message) or recipient_id == message.from_agent_id:
        return False
    sender, recipient = agents.get(uow, message.from_agent_id), agents.get(uow, recipient_id)
    if (not sender or not sender.is_active or not recipient or not recipient.is_active
            or not runtime_enabled or not has_runtime(uow, recipient_id, message.workspace_id)):
        return False
    if notifications is None:
        raise RuntimeError('Handoff notification persistence is not configured.')
    # The UNIQUE key of migration 113 has no epoch column. The epoch rides in event_type.
    event = f'{kind}:{handoff.claim_epoch}'
    if uow.connection.execute('SELECT 1 FROM runtime_handoff_notifications WHERE handoff_id=? '
            'AND recipient_agent_id=? AND event_type=?', (handoff.handoff_id, recipient_id, event)).fetchone():
        return False
    notifications.record(uow, message_id=message.message_id, handoff_id=handoff.handoff_id,
        recipient_id=recipient_id, event_type=event,
        actor_guard=_agent_guard(uow.connection, message.from_agent_id), competitive=False)
    context = RuntimeRequestContext(message.from_agent_id, 'handoff_notification',
                                    credential_binding=PREFIX + message.message_id)
    uow.connection.execute('INSERT INTO runtime_pending_deliveries(delivery_id,context_json,authorization_revision,created_at) VALUES(?,?,?,?)',
        (delivery.delivery_id, json.dumps(asdict(context)), 'handoff-notification', now))
    return True


def valid_binding(uow, actor, binding, workspace_id):
    row = uow.connection.execute(
        'SELECT n.actor_guard,n.runtime_route,m.from_agent_id,m.workspace_id FROM runtime_handoff_notifications n '
        'JOIN messages m USING(message_id) WHERE n.message_id=?', (binding[len(PREFIX):],)).fetchone()
    return bool(row and row['runtime_route'] != 'competitive'
                and row['from_agent_id'] == actor.agent_id and row['workspace_id'] == workspace_id
                and row['actor_guard'] == _agent_guard(uow.connection, actor.agent_id))


def validate(uow, *, message, recipient_id, agents, now, governance=None):
    row = uow.connection.execute('SELECT * FROM runtime_handoff_notifications WHERE message_id=? AND recipient_agent_id=?',
                                 (message.message_id, recipient_id)).fetchone()
    record = uow.connection.execute('SELECT * FROM handoffs WHERE handoff_id=? AND workspace_id=?',
        (row['handoff_id'], message.workspace_id)).fetchone() if row else None
    handoff = SimpleNamespace(**dict(record)) if record else None
    if row and row['runtime_route'] in {'competitive', 'legacy_admitted'}:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Competitive handoff notices use the runtime scheduler.',
                            {'reason': 'competitive_handoff_control'})
    if row and row['event_type'].split(':')[0] in OUTCOME_KINDS:
        sender, recipient = agents.get(uow, message.from_agent_id), agents.get(uow, recipient_id)
        if (not handoff or recipient_id not in _participants(handoff, message) or not sender or not sender.is_active
                or not recipient or not recipient.is_active):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Handoff notification is no longer available to this recipient.', {})
        return
    if (not handoff or handoff.status != 'OPEN' or not eligible(uow, agents=agents, handoff=handoff,
                                                              recipient_id=recipient_id, now=now, governance=governance)):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Handoff notification is no longer available to this recipient.', {})
