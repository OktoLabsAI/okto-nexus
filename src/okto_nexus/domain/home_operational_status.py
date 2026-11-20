"""Negotiated operational reduction over authorized facts, without effects.

In particular, native write success is never an acknowledgement of application.
No wall-clock ordering of receipt arrivals can supply that missing causal fact.
"""
from .attention import instant
from .home_harness_blocking import FIELDS, TERMINAL

KINDS = ('question', 'approval', 'decision', 'verification')


def count(value, exact=True):
    return {'value': value if exact else None, 'total_is_exact': exact}


def action_kind(occurrence):
    actions = set(occurrence.get('allowed_actions', ()))
    if 'respond_native' in actions or 'question' in occurrence['kind']:
        return 'question'
    if 'verify' in occurrence['kind'] or 'verification' in occurrence['kind']:
        return 'verification'
    if 'approval' in occurrence['kind'] or 'permission' in occurrence['kind']:
        return 'approval'
    return 'decision'


def human_action(o):
    # active is a reminder preference; it does not settle the human obligation.
    return (o['category'] == 'action_required' and o['freshness'] == 'current'
            and o['resolution'] == 'open' and bool(o['allowed_actions']))


def project(relations, registry, *, now, check_budget):
    occurrences = {}
    for entry in relations.entries:
        check_budget()
        for o in entry.attention:
            check_budget()
            if o['source_type'] == 'execution_native_request':
                occurrences[o['source_id']] = o
    sessions, operations, requests = {}, {}, {}
    for session in relations.operational_sessions or ():
        check_budget()
        key = tuple(getattr(session, field) for field in FIELDS)
        sessions.setdefault(key, {})[session.session_id] = session
    for row in relations.harness_blocking or ():
        check_budget()
        key = tuple(row.get(field) for field in FIELDS)
        if key not in registry:
            continue
        if row['family'] == 'operation':
            operations.setdefault(key, {})[row['operation_id']] = row
        else:
            requests.setdefault(key, []).append(row)
    complete = (relations.operational_sessions is not None and relations.harness_blocking is not None
                and all(relations.source_status.get(k) == 'ready' for k in ('connections', 'sessions', 'correlations')))
    actions_exact = relations.source_status.get('attention') == 'ready'
    states, ownership, waiting = {}, {}, {}
    for key in registry:
        check_budget()
        own_sessions = sessions.get(key, {})
        live = {sid: s for sid, s in own_sessions.items() if s.authority_current and s.control_current and s.runtime_ready and s.valid_until
                and instant(s.valid_until) > instant(now)}
        ops = operations.get(key, {})
        pending = {oid: o for oid, o in ops.items() if o['stage'] not in TERMINAL
                   and o['admission_state'] != 'REJECTED' and o['dispatch_state'] != 'RESOLVED_NOT_SENT'}
        blockers, confirmations, refusals, owned_actions, session_blocks = {}, [], [], {}, {}
        response_uncertain = False
        uncertain = {oid for oid, o in pending.items() if o['stage'] == 'OUTCOME_UNKNOWN'
                     or o['dispatch_state'] == 'RECONCILING'}
        for row in requests.get(key, ()):
            check_budget()
            session = own_sessions.get(row['session_id'])
            operation = ops.get(row['operation_id'])
            occurrence = occurrences.get(row['request_id'])
            scoped = bool(session and operation and operation['session_id'] == session.session_id
                and row.get('owner_generation') == session.owner_generation
                and row['stream_epoch'] == session.stream_epoch == row['session_stream_epoch'])
            if scoped and occurrence and all(occurrence.get(name) == row.get(name)
                    for name in ('executor_id', 'session_id', 'operation_id', 'workspace_id', 'agent_id')):
                ownership[occurrence['attention_id']] = {key}
                if human_action(occurrence):
                    owned_actions[occurrence['attention_id']] = occurrence
            proven_method = (row.get('adapter_id') == 'codex_app_server'
                             and row['method'] == 'item/tool/requestUserInput')
            current = (scoped and row['session_id'] in live and row['state'] == 'PENDING'
                       and instant(row['expires_at']) > instant(now) and row['operation_id'] in pending)
            if current and proven_method and occurrence and row['is_blocking'] in (0, 1):
                session_blocks[occurrence['attention_id']] = bool(row['is_blocking'])
            if current and proven_method and row['is_blocking'] == 1:
                blockers.setdefault(row['operation_id'], []).append(row)
                if occurrence and occurrence['attention_id'] in owned_actions:
                    waiting[occurrence['attention_id']] = occurrence
            elif current and proven_method and row['is_blocking'] == 0:
                pass
            elif row['operation_id'] in pending and row['state'] in ('PENDING', 'DECIDED'):
                uncertain.add(row['operation_id'])
            # A same-epoch decision of the exact originally blocking request is
            # observable even when the old productive RUNNING arrives later.
            if (scoped and session.authority_current and proven_method and row['is_blocking'] == 1 and row['state'] == 'DECIDED'
                    and row.get('decision_id') and row.get('native_operation_id')
                    and row.get('decision_scope_matches') == 1
                    and row['operation_id'] in pending):
                ref = {'request_id': row['request_id'], 'decision_id': row['decision_id'],
                    'operation_id': row['operation_id'], 'session_id': row['session_id'], 'stream_epoch': row['stream_epoch']}
                refused = row.get('native_write_stage') in ('FAILED', 'CANCELLED') and row.get('native_write_possible_effect') == 0
                (refusals if refused else confirmations).append(ref)
                response_uncertain = response_uncertain or row.get('native_write_stage') == 'OUTCOME_UNKNOWN' or row.get('native_write_dispatch') == 'RECONCILING'
                uncertain.add(row['operation_id'])
        running = {o['session_id'] for oid, o in pending.items() if (o['stage'] == 'RUNNING'
                   or o['stage'] in ('SUBMITTED', 'ACCEPTED') and o.get('productive_progress_current') is True)
                   and o['session_id'] in live and oid not in blockers and oid not in uncertain
                   and o.get('owner_generation') == live[o['session_id']].owner_generation
                   and o.get('stream_epoch') == live[o['session_id']].stream_epoch}
        blocked_sessions = {r['session_id'] for rows in blockers.values() for r in rows}
        sessions_accounted = all(sid in live or s.lifecycle_state == 'CLOSED' for sid, s in own_sessions.items())
        native_full = bool(complete and actions_exact and sessions_accounted and pending and not uncertain
                           and all(oid in blockers for oid in pending))
        full = native_full and all(occurrences.get(r['request_id'], {}).get('attention_id') in owned_actions
                                  for rows in blockers.values() for r in rows)
        waiting_agent = native_full and all(occurrences.get(r['request_id'], {}).get('kind') == 'question_waiting_for_agent'
                                           for rows in blockers.values() for r in rows)
        connection = ('connected' if live else 'disconnected' if any(s.revoked for s in own_sessions.values())
                      else 'registered' if complete and not own_sessions else 'unknown')
        activity, reason, placement = 'unknown', 'INSUFFICIENT_CURRENT_PROOF', 'monitoring_unconfirmed'
        blocks, blocking = None, 'unknown'
        if running:
            activity, blocks, blocking = 'working', False, 'partial' if blockers else 'none'
            reason, placement = 'CURRENT_PRODUCTIVE_OPERATION', 'normal_monitoring'
        elif full:
            activity, blocks, blocking = 'waiting_user', True, 'full'
            reason, placement = 'ALL_PENDING_WORK_BLOCKED', 'human_block_confirmed'
        elif waiting_agent:
            activity, reason = 'waiting_agent', 'REQUEST_DIRECTED_TO_AGENT'
        elif refusals:
            reason = 'NATIVE_RESPONSE_NOT_APPLIED'
        elif confirmations:
            activity, reason = 'awaiting_confirmation', 'NATIVE_APPLICATION_UNCONFIRMED'
            if response_uncertain:
                reason = 'NATIVE_RESPONSE_OUTCOME_UNKNOWN'
            confirmed_ops = {r['operation_id'] for r in confirmations}
            if (complete and actions_exact and sessions_accounted and all(o['session_id'] in live for o in pending.values())
                    and set(pending) <= confirmed_ops):
                placement = 'awaiting_native_confirmation'
        elif pending and not uncertain and all(o['stage'] is None and o['dispatch_state'] in ('PENDING', 'RESERVED') for o in pending.values()):
            activity, reason = 'queued', 'QUEUED_NOT_PRODUCTIVE'
        elif (complete and actions_exact and sessions_accounted and live and all(s.persistent_runtime for s in live.values())
              and not pending and not owned_actions):
            activity, blocks, blocking = 'idle', False, 'none'
            reason, placement = 'LIVE_SESSION_NO_PENDING_WORK', 'normal_monitoring'
        elif complete and own_sessions and all(s.lifecycle_state == 'CLOSED' for s in own_sessions.values()) and not pending:
            activity, blocks, blocking = 'no_active_session', False, 'none'
            reason = 'ALL_SESSIONS_CLOSED'
        freshness = 'current' if live else 'unavailable' if relations.operational_sessions is None else 'stale'
        status = {'version': 1, 'connection': connection, 'activity': activity, 'blocking': blocking,
            'freshness': freshness, 'as_of': max((s.observed_at for s in live.values() if s.observed_at), default=None),
            'state_since': None, 'reason_code': reason, 'pending_actions': count(len(owned_actions), actions_exact),
            'pending_by_kind': {kind: count(sum(action_kind(o) == kind for o in owned_actions.values()), actions_exact) for kind in KINDS},
            'pending_request_ids': sorted(owned_actions), 'has_more_pending_requests': False, 'pending_requests_cursor': None,
            'running_sessions': count(len(running), complete and not uncertain), 'blocked_sessions': count(len(blocked_sessions), complete and not uncertain),
            'awaiting_native_confirmation': bool(confirmations)}
        states[key] = {'blocks_harness': blocks,
            'activity_state': {'waiting_user': 'waiting_for_user', 'idle': 'registered', 'queued': 'unknown',
                            'waiting_agent': 'unknown', 'no_active_session': 'registered'}.get(activity, activity),
            'blocking_request_ids': sorted(o['attention_id'] for o in owned_actions.values() if o['attention_id'] in waiting),
            'reminder_snoozed': any(o.get('seen_state', {}).get('snoozed', False) for o in owned_actions.values()),
            'operational_status': status, 'placement_reason': placement, 'resume_confirmation_refs': confirmations + refusals,
            '_session_blocks': session_blocks}
    return states, ownership, waiting
