"""Server status replies for proven session release without a final result.

The original admitted conversation supplies every identity. These notices are
not native output, acknowledgements, successful handoff completion or automatic
runtime relays. One-shot calls already own a separate error-notification path.
"""
import hashlib
import json
from dataclasses import dataclass

from ..domain.messages import MESSAGE_CREATED_TYPE, MESSAGE_STREAM


def publish_release_notifications(deps, messages):
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        rows = conn.execute(
            "SELECT r.domain_operation_id,r.operation_id,r.session_id,d.workspace_id,"
            "d.message_id,d.recipient_agent_id,m.from_agent_id AS caller_id,m.channel_id "
            "FROM execution_release_notifications n INDEXED BY execution_release_notifications_pending "
            "CROSS JOIN execution_delivery_releases r ON r.domain_operation_id=n.domain_operation_id "
            "CROSS JOIN execution_sessions s USING(server_id,executor_id,session_id) "
            "CROSS JOIN execution_operations o USING(server_id,executor_id,operation_id) "
            "CROSS JOIN execution_domain_deliveries x USING(server_id,executor_id,operation_id) "
            "CROSS JOIN delivery_outbox d ON d.operation_id=r.domain_operation_id "
            "CROSS JOIN messages m ON m.message_id=d.message_id "
            "WHERE n.state='PENDING' AND x.domain_operation_id=r.domain_operation_id AND o.session_id=r.session_id "
            "AND o.action='turn.submit' AND o.subject_agent_id=d.recipient_agent_id "
            "AND s.lifecycle_state='CLOSED' AND s.lease_state='CLOSED' "
            "AND d.workspace_id=m.workspace_id AND d.actor_agent_id=m.from_agent_id "
            "AND d.reconciliation_id IS NULL AND d.canonical_terminal_operation_id IS NULL "
            "AND d.terminal_event_id IS NULL AND d.external_completed_at IS NULL "
            "AND d.status='OUTCOME_UNKNOWN' AND d.reason='session_released_without_result' "
            "AND NOT EXISTS (SELECT 1 FROM one_shot_calls c WHERE c.call_id=r.domain_operation_id) "
            "AND NOT EXISTS (SELECT 1 FROM runtime_handoff_notice_retirements n "
            "WHERE n.operation_id=r.domain_operation_id) "
            "AND NOT EXISTS (SELECT 1 FROM execution_capacity_compensations c "
            "WHERE c.domain_operation_id=r.domain_operation_id) "
            "ORDER BY n.created_at,n.domain_operation_id LIMIT 32").fetchall()
        for row in rows:
            identity = hashlib.sha256(row['domain_operation_id'].encode()).hexdigest()
            message_id = 'msg_runtime_release_' + identity
            target = dict(strategy='direct', agent_id=row['caller_id'])
            now = deps.clock.now_iso()
            subject = 'Nexus runtime interrupted'
            body = (
                'RUNTIME_SESSION_ENDED: The runtime session ended before a final response was recorded. '
                'The session has been closed and this request will not be replayed automatically. '
                'Actions may already have taken effect; check their outcome before retrying.\n\n'
                f"Request: {row['domain_operation_id']}\nSession: {row['session_id']}")
            messages._messages.create(uow, message_id=message_id, workspace_id=row['workspace_id'],
                from_agent_id=row['recipient_agent_id'], channel_id=row['channel_id'], from_session_id=None,
                target=json.dumps(target), subject=subject, body=body, artifacts=[],
                parent_message_id=row['message_id'], trace_id=None, created_at=now)
            messages._deliveries.create(uow, delivery_id='del_runtime_release_' + identity,
                message_id=message_id, recipient_agent_id=row['caller_id'], status='unread', created_at=now)
            messages._emitter.emit(uow, workspace_id=row['workspace_id'], stream=MESSAGE_STREAM,
                type=MESSAGE_CREATED_TYPE, payload=dict(message_id=message_id, channel_id=row['channel_id'],
                    from_agent_id=row['recipient_agent_id'], target=target, subject=subject, created_at=now,
                    runtime_operation_id=row['domain_operation_id'], system_notification=True),
                actor_agent_id=None, visibility='eligible', target=json.dumps(target))
            conn.execute("UPDATE execution_release_notifications SET message_id=?,state='PUBLISHED' "
                "WHERE domain_operation_id=? AND state='PENDING'", (message_id, row['domain_operation_id']))
        return len(rows)


def notify_contained_claimant(deps, messages, *, server_id, executor_id, session_id, agent_id, reason):
    """Record why a session was contained and tell the operator and the waiting creators.

    Each CLAIMED handoff of the agent gets one notice to its creator. The
    operator always gets one notice with the agent, the reason and the session.
    It lists the claimed handoffs when there are any. The reason, the notices and
    the event commit together. A second call for the same session does nothing.
    These notices are inbox messages. They do not start a runtime turn.
    """
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        recorded = conn.execute(
            "SELECT containment_reason,workspace_id FROM execution_sessions WHERE server_id=? AND executor_id=? AND session_id=?",
            (server_id, executor_id, session_id)).fetchone()
        if recorded is not None and recorded[0] is not None:
            return 0
        now = deps.clock.now_iso()
        if recorded is not None:
            conn.execute("UPDATE execution_sessions SET containment_reason=?,contained_at=? "
                "WHERE server_id=? AND executor_id=? AND session_id=?",
                (reason, now, server_id, executor_id, session_id))
        handoffs = conn.execute(
            "SELECT handoff_id,workspace_id,from_agent_id,lease_expires_at,updated_at FROM handoffs "
            "WHERE status='CLAIMED' AND claimed_by=? ORDER BY created_at,handoff_id", (agent_id,)).fetchall()
        sent = 0

        def send(recipient_id, handoff_id, workspace_id, subject, body):
            nonlocal sent
            if workspace_id is None or deps.repos.agents.get(uow, recipient_id) is None:
                return
            identity = hashlib.sha256(f'{session_id}|{handoff_id}|{recipient_id}'.encode()).hexdigest()
            message_id = 'msg_claimant_contained_' + identity
            target = dict(strategy='direct', agent_id=recipient_id)
            messages._messages.create(uow, message_id=message_id, workspace_id=workspace_id,
                from_agent_id=agent_id, channel_id=None, from_session_id=None, target=json.dumps(target),
                subject=subject, body=body, artifacts=[], parent_message_id=None, trace_id=None, created_at=now)
            messages._deliveries.create(uow, delivery_id='del_claimant_contained_' + identity,
                message_id=message_id, recipient_agent_id=recipient_id, status='unread', created_at=now)
            messages._emitter.emit(uow, workspace_id=workspace_id, stream=MESSAGE_STREAM,
                type=MESSAGE_CREATED_TYPE, payload=dict(message_id=message_id, channel_id=None,
                    from_agent_id=agent_id, target=target, subject=subject, created_at=now,
                    system_notification=True), actor_agent_id=None, visibility='eligible',
                target=json.dumps(target))
            sent += 1

        for handoff in handoffs:
            creator = handoff['from_agent_id']
            if creator and creator not in (agent_id, 'operator'):
                send(creator, handoff['handoff_id'], handoff['workspace_id'], f"handoff {handoff['handoff_id']} claimant session contained",
                    f"Claimant session contained (reason: {reason}). "
                    f"Work after {handoff['updated_at']} may be lost. "
                    f"The lease of {agent_id} runs to {handoff['lease_expires_at']}.\n\n"
                    f"Handoff: {handoff['handoff_id']}\nClaimant: {agent_id}\nSession: {session_id}")
        lines = ''.join(f"\nHandoff: {h['handoff_id']} (lease to {h['lease_expires_at']})" for h in handoffs)
        affected = (f"Work of {agent_id} on {len(handoffs)} claimed handoff(s) may be lost.{lines}\n\n"
            if handoffs else f"{agent_id} holds no claimed handoff.\n\n")
        workspace_id = handoffs[0]['workspace_id'] if handoffs else (
            recorded['workspace_id'] if recorded is not None else None)
        send('operator', '', workspace_id, f'claimant session of {agent_id} contained',
            f"Claimant session contained (reason: {reason}). {affected}"
            f"Claimant: {agent_id}\nSession: {session_id}")
        return sent


@dataclass(frozen=True)
class InstallationUpdate:
    """One row of execution_installation_succession, as the notifier needs it."""
    server_id: str
    executor_id: str
    stable_ref: str
    decision: str
    reason: str | None = None
    from_version: str | None = None
    to_version: str | None = None
    from_build_identity: str | None = None
    to_build_identity: str | None = None


def notify_installation_update(deps, messages, update):
    """Tell the operator that a runtime installation was accepted or held.

    The hub sends one inbox message per affected workspace. The message names
    the agents bound to the installation, both versions, the first 12 hex
    characters of both build identities, the decision and the held reason.
    The message id comes from the ref, the new build, the decision and the
    workspace. A repeated call for the same update sends nothing.
    These notices are inbox messages. They do not start a runtime turn.
    """
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        rows = conn.execute(
            "SELECT DISTINCT e.workspace_id,e.agent_id FROM execution_bindings b "
            "JOIN agent_endpoints e USING(endpoint_id) "
            "WHERE b.server_id=? AND b.executor_id=? AND b.candidate_ref=? AND e.workspace_id IS NOT NULL "
            "ORDER BY e.workspace_id,e.agent_id",
            (update.server_id, update.executor_id, update.stable_ref)).fetchall()
        agents = {}
        for row in rows:
            agents.setdefault(row['workspace_id'], []).append(row['agent_id'])
        short = lambda value: (value or 'unknown')[:12]
        now = deps.clock.now_iso()
        sent = 0
        for workspace_id, names in agents.items():
            if deps.repos.agents.get(uow, 'operator') is None:
                break
            identity = hashlib.sha256('|'.join(
                (update.stable_ref, update.to_build_identity or '', update.decision, workspace_id)).encode()).hexdigest()
            message_id = 'msg_installation_update_' + identity
            if conn.execute("SELECT 1 FROM messages WHERE message_id=?", (message_id,)).fetchone() is not None:
                continue
            target = dict(strategy='direct', agent_id='operator')
            subject = f'runtime installation update {update.decision}'
            body = (
                f"Runtime installation update {update.decision}.\n"
                f"Agents: {', '.join(names)}\n"
                f"Version: {update.from_version or 'unknown'} to {update.to_version or 'unknown'}\n"
                f"Build identity: {short(update.from_build_identity)} to {short(update.to_build_identity)}\n"
                f"Decision: {update.decision}\n")
            if update.decision == 'held':
                body += (f"Held reason: {update.reason or 'unknown'}\n"
                    "New sessions stay blocked until the operator accepts the update.\n")
            messages._messages.create(uow, message_id=message_id, workspace_id=workspace_id,
                from_agent_id='operator', channel_id=None, from_session_id=None, target=json.dumps(target),
                subject=subject, body=body, artifacts=[], parent_message_id=None, trace_id=None, created_at=now)
            messages._deliveries.create(uow, delivery_id='del_installation_update_' + identity,
                message_id=message_id, recipient_agent_id='operator', status='unread', created_at=now)
            messages._emitter.emit(uow, workspace_id=workspace_id, stream=MESSAGE_STREAM,
                type=MESSAGE_CREATED_TYPE, payload=dict(message_id=message_id, channel_id=None,
                    from_agent_id='operator', target=target, subject=subject, created_at=now,
                    system_notification=True), actor_agent_id=None, visibility='eligible',
                target=json.dumps(target))
            sent += 1
        return sent
