"""Conservative current request placement from metadata, never preferences."""
from .attention import instant

FIELDS = ('server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id')
TERMINAL = frozenset(('SUCCEEDED', 'FAILED', 'CANCELLED', 'REJECTED'))


def project_v2(relations, registry, *, now, check_budget):
    from .home_operational_status import project as operational_project
    return operational_project(relations, registry, now=now, check_budget=check_budget)


def project(relations, registry, *, now, check_budget):
    occurrences = {}
    for entry in relations.entries:
        check_budget()
        for occurrence in entry.attention:
            check_budget()
            if occurrence['source_type'] == 'execution_native_request':
                occurrences[occurrence['source_id']] = occurrence
    operations, requests, request_keys, waiting = {}, {}, {}, {}
    for row in relations.harness_blocking or ():
        check_budget()
        key = tuple(row.get(name) for name in FIELDS)
        if key not in registry:
            continue
        if row['family'] == 'operation':
            operations.setdefault(key, {})[row['operation_id']] = row
        else:
            requests.setdefault(key, []).append(row)
    complete = relations.harness_blocking is not None and relations.connections is not None and all(
        relations.source_status.get(name) == 'ready' for name in ('attention', 'work', 'sessions', 'correlations'))
    result = {}
    for key in registry:
        check_budget()
        ops = operations.get(key, {})
        pending = {identifier: row for identifier, row in ops.items() if row['stage'] not in TERMINAL
            and row['admission_state'] != 'REJECTED' and row['dispatch_state'] != 'RESOLVED_NOT_SENT'}
        blocking, undecidable, confirmation = {}, set(), False
        for row in requests.get(key, ()):
            check_budget()
            occurrence = occurrences.get(row['request_id'])
            operation = pending.get(row['operation_id'])
            # The same authorized read UoW supplies both occurrence revision and
            # request metadata. No mutation or cross-request revision reuse.
            scoped = bool(occurrence and operation and occurrence['executor_id'] == row['executor_id']
                and occurrence['session_id'] == row['session_id'] == operation['session_id']
                and occurrence['operation_id'] == row['operation_id']
                and occurrence['workspace_id'] == row['workspace_id']
                and occurrence['agent_id'] == row['agent_id'])
            if scoped:
                request_keys[occurrence['attention_id']] = {key}
            current = bool(scoped and row['state'] == 'PENDING' and row['approval_status'] == 'pending'
                and row['stream_epoch'] == row['session_stream_epoch']
                and instant(row['expires_at']) > instant(now)
                and occurrence['category'] == 'action_required' and occurrence['freshness'] == 'current'
                and occurrence['resolution'] == 'open' and occurrence['allowed_actions'])
            proven_method = row['method'] == 'item/tool/requestUserInput'
            if current and proven_method and row['is_blocking'] == 1:
                blocking.setdefault(row['operation_id'], []).append(occurrence)
                waiting[occurrence['attention_id']] = occurrence
            elif operation and row['state'] == 'PENDING' and (not current or not proven_method or row['is_blocking'] is None) or operation and row['is_blocking'] == 1 and not current:
                undecidable.add(row['operation_id'])
            if operation and row['is_blocking'] == 1 and row['decided_at'] and (
                    operation['received_at'] is None or instant(operation['received_at']) <= instant(row['decided_at'])):
                confirmation = True
        uncertain = any(row['stage'] == 'OUTCOME_UNKNOWN' or row['stage'] is None and identifier not in blocking
                        or row['dispatch_state'] == 'RECONCILING' for identifier, row in pending.items())
        if not complete:
            state, activity = None, 'unknown'
        elif any(row['stage'] == 'RUNNING' and identifier not in blocking and identifier not in undecidable
                 for identifier, row in pending.items()):
            state, activity = False, 'working'
        elif uncertain:
            state, activity = None, 'unknown'
        elif pending and all(identifier in blocking for identifier in pending):
            state, activity = True, 'waiting_for_user'
        elif confirmation:
            state, activity = None, 'awaiting_confirmation'
        elif pending:
            state, activity = None, 'unknown'
        else:
            state, activity = False, 'registered'
        pending_occurrences = [occurrence for items in blocking.values() for occurrence in items]
        result[key] = dict(blocks_harness=state, activity_state=activity,
            blocking_request_ids=[o['attention_id'] for o in pending_occurrences],
            reminder_snoozed=any(o.get('seen_state', {}).get('snoozed', False) for o in pending_occurrences))
    return result, request_keys, waiting
