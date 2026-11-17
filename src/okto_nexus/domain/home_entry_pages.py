"""Versioned pages over complete authorized entry relations, never page merges.

Cursors are base64 JSON with validated bindings, NOT cryptographic signatures.
Every continuation reauthorizes and recomputes the material revision.
"""
import base64
import json
from dataclasses import fields
from datetime import timedelta

from ..errors import ErrorCode, OktoNexusError
from .attention import canonical, digest, instant
from .home import filters as home_filters
from .home import identity, invalid
from .home import limit as page_limit

QUICK = frozenset({'active', 'needs_you', 'results', 'all'})
PASSIVE = frozenset({'configured', 'connected', 'idle', 'offline', 'stale'})
TERMINAL = frozenset({'completed', 'turn_completed', 'failed', 'cancelled'})


def filters(value=None):
    value = value or {}
    if type(value) is not dict or set(value) - {'workspace_id', 'agent_id', 'state', 'quick', 'harness', 'host'}:
        invalid('Invalid Home entries filters.')
    base = {k: v for k, v in value.items() if k in {'workspace_id', 'agent_id', 'state'}}
    passive = type(base.get('state')) is str and base['state'] in PASSIVE
    if passive:
        base.pop('state')
    result = home_filters(base)
    if passive:
        result['state'] = value['state']
    quick = value.get('quick', 'active')
    if type(quick) is not str or quick not in QUICK:
        invalid('Invalid Home entries quick filter.')
    result['quick'] = quick
    # Read-only normalized metadata, deliberately not an accepted query filter.
    result['include_recent_results'] = 'quick' not in value
    for key in ('harness', 'host'):
        if value.get(key) is not None:
            result[key] = identity(value[key])
    return result


def conflict(message='Home entries changed. Reload the first page.'):
    raise OktoNexusError(ErrorCode.CONFLICT, message, {'reason': 'HOME_ENTRIES_SNAPSHOT_CHANGED'})


def cursor_encode(binding, revision, key):
    return base64.urlsafe_b64encode(canonical(dict(v=1, binding=binding, revision=revision, key=key)).encode()).decode().rstrip('=')


def _cursor_binding(value):
    required = {'server_id', 'principal', 'scope', 'partition', 'group_id', 'entry_id'}
    if set(value) not in (required, required | {'presentation_version'}):
        raise ValueError
    if 'presentation_version' in value and (type(value['presentation_version']) is not int or value['presentation_version'] != 2):
        raise ValueError
    for key in ('server_id', 'principal', 'partition'):
        if type(value[key]) is not str:
            raise ValueError
    for key in ('group_id', 'entry_id'):
        if value[key] is not None and type(value[key]) is not str:
            raise ValueError
    scope = value['scope']
    if (type(scope) is not dict or set(scope) - {'workspace_id', 'agent_id', 'state', 'quick', 'include_recent_results', 'harness', 'host'}
            or not {'workspace_id', 'quick', 'include_recent_results'} <= set(scope)
            or type(scope['include_recent_results']) is not bool):
        raise ValueError
    for key, item in scope.items():
        if key == 'include_recent_results' or key == 'workspace_id' and item is None:
            continue
        if type(item) is not str:
            raise ValueError


def cursor_decode(value, binding, revision):
    if value is None:
        return None
    try:
        if type(value) is not str or len(value) > 4096:
            raise ValueError
        data = json.loads(base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True))
        if (type(data) is not dict or set(data) != {'v', 'binding', 'revision', 'key'} or type(data['v']) is not int or data['v'] != 1
                or type(data['binding']) is not dict or type(data['revision']) is not str
                or type(data['key']) is not list or len(data['key']) != 3
                or type(data['key'][0]) is not int or any(type(x) is not str for x in data['key'][1:])):
            raise ValueError
        _cursor_binding(data['binding'])
        matches = canonical(data['binding']) == canonical(binding)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        invalid('Invalid Home entries cursor.')
    if not matches:
        conflict('Home entries cursor belongs to a different scope or parent.')
    if data['revision'] != revision:
        conflict()
    return tuple(data['key'])


def entry_key(entry):
    actionable = any(o['active'] and o['freshness'] == 'current' and o['category'] == 'action_required' for o in entry.attention)
    priority = 0 if actionable else 1 if entry.display_state in ('outcome_unknown', 'failed') else 2 if entry.display_state == 'running' else 5 if entry.display_state in PASSIVE else 4 if entry.display_state in TERMINAL else 3
    timestamp = entry.activity['last_activity_at'] if entry.activity else next((r['created_at'] for r in entry.results), None)
    # ISO strings are canonical UTC. Negative epoch gives newest first without
    # interpolating arbitrary text into SQL or depending on locale sorting.
    temporal = f'{10**16 - int(instant(timestamp).timestamp()*1_000_000):020d}' if timestamp else '99999999999999999999'
    return priority, temporal, entry.id


def _newest(value):
    return f'{10**16 - int(instant(value).timestamp()*1_000_000):020d}' if value else '99999999999999999999'


def attention_key(item):
    human = item['active'] and item['freshness'] == 'current' and item['resolution'] == 'open' and item['category'] == 'action_required'
    return (0 if human else 1, _newest(item['last_changed_at']), item['attention_id'])


def result_key(item):
    return (0 if item['view_state'] == 'unseen' else 1, _newest(item['created_at']), item['id'])


def selected(entry, scope, now):
    connection = entry.connection
    if scope.get('harness') is not None and (connection is None or connection.harness_id != scope['harness']):
        return False
    if scope.get('host') is not None and (connection is None or connection.executor_id != scope['host']):
        return False
    if scope.get('state') not in (None, 'all', entry.display_state):
        return False
    quick = scope['quick']
    if quick == 'needs_you':
        return any(o['active'] and o['freshness'] == 'current' and o['category'] == 'action_required' and
                   o['resolution'] == 'open' for o in entry.attention)
    if quick == 'results':
        return bool(entry.results)
    if quick == 'active':
        if scope['include_recent_results'] and entry.kind in ('connection', 'session') and entry.connection is not None:
            return True
        if scope['include_recent_results'] and any(result['view_state'] == 'unseen' or
                result['view_state'] == 'not_tracked' or
                result['created_at'] and instant(result['created_at']) >= instant(now) - timedelta(hours=24)
                for result in entry.results):
            return True
        return entry.display_state not in TERMINAL and (entry.kind == 'work' or entry.display_state not in ('offline', 'stale', 'configured'))
    return True


def revision(relations, check_budget):
    # Relations are fixed for this read UoW. Their JSON rows need no recursive
    # deepcopy; only the dataclass contexts need conversion. Keep references in
    # these per-call caches so aliases are cheap without risking id reuse or
    # retaining a snapshot across reads/principals.
    contexts, row_keys = {}, {}

    def context_value(context):
        if context is None:
            return None
        identifier = id(context)
        if identifier not in contexts:
            contexts[identifier] = (context, {f.name: getattr(context, f.name) for f in fields(context)})
        return contexts[identifier][1]

    def row_key(row):
        identifier = id(row)
        if identifier not in row_keys:
            row_keys[identifier] = (row, canonical(row))
        return row_keys[identifier][1]

    entries = []
    for entry in sorted(relations.entries, key=lambda item: item.id):
        check_budget()
        value = {f.name: getattr(entry, f.name) for f in fields(entry)}
        value['connection'] = context_value(entry.connection)
        value['sessions'] = tuple(context_value(s) for s in entry.sessions)
        value['registered_connections'] = tuple(context_value(c) for c in entry.registered_connections)
        for name, key in (('operations', 'operation_id'), ('attention', 'attention_id'), ('results', 'id'), ('external', 'observed_instance_id')):
            value[name] = sorted(value[name], key=lambda row, key=key: (row[key], row_key(row)))
        entries.append(value)
    result = digest(dict(entries=entries, server_attention=sorted(relations.server_attention, key=lambda row: row['attention_id']),
                         source_status=relations.source_status, connection_count=relations.connection_count,
                         connections=None if relations.connections is None else sorted(
                             (context_value(c) for c in relations.connections), key=row_key)))
    check_budget()
    return result


def session_ref(session):
    value = {key: getattr(session, key) for key in ('server_id', 'executor_id', 'workspace_id', 'session_id')}
    from .home_entries import SessionRuntimeFact
    if isinstance(session, SessionRuntimeFact):
        value.update(lifecycle_state=session.lifecycle_state, title=session.title or 'Session',
            workspace_label=session.workspace_label, last_activity_at=session.observed_at)
    return value


def entry_dto(entry, *, binding, revision, group_id, now, refresh_at, preview=3, sessions_exact=True, attention_exact=True, results_exact=True):
    sessions = sorted(entry.sessions, key=lambda s: (s.executor_id, s.session_id))
    more = len(sessions) > preview
    session_binding = dict(binding, partition='sessions', group_id=group_id, entry_id=entry.id)
    attention = sorted(entry.attention, key=attention_key)
    results = sorted(entry.results, key=result_key)
    attention_preview, results_preview = attention[:3], results[:3]
    attention_binding = dict(binding, partition='attention', group_id=group_id, entry_id=entry.id)
    result_binding = dict(binding, partition='results', group_id=group_id, entry_id=entry.id)
    return dict(id=entry.id, kind=entry.kind, source_ref=entry.source_ref,
        workspace_id=entry.workspace_id, agent_id=entry.agent_id, title=entry.title,
        agent_label=entry.connection.agent_label if entry.connection else None,
        harness_label=entry.connection.harness_id if entry.connection else None,
        host_label=entry.connection.host_label if entry.connection else None,
        display_state=entry.display_state, evidence=entry.evidence,
        state_since=entry.activity['state_since'] if entry.activity else None,
        sessions=[session_ref(s) for s in sessions[:preview]], sessions_total=len(sessions) if sessions_exact else None,
        has_more_sessions=more,
        sessions_cursor=cursor_encode(session_binding, revision, [0, sessions[preview-1].executor_id, sessions[preview-1].session_id]) if more else None,
        attention_preview=attention_preview, attention_total=len(attention) if attention_exact else None,
        has_more_attention=len(attention)>3,
        attention_cursor=cursor_encode(attention_binding, revision, list(attention_key(attention_preview[-1]))) if len(attention)>3 else None,
        results_preview=results_preview, results_total=len(results) if results_exact else None,
        has_more_results=len(results)>3,
        results_cursor=cursor_encode(result_binding, revision, list(result_key(results_preview[-1]))) if len(results)>3 else None,
        related_coverage=dict(attention='ready' if attention_exact else 'unknown', results='ready' if results_exact else 'unknown'),
        attention_refs=[o['attention_id'] for o in attention_preview],
        result_refs=[r['id'] for r in results_preview], target=entry.target,
        result_tracking='unseen' if any(r['view_state'] == 'unseen' for r in entry.results) else
            'unknown' if any(r['view_state'] == 'not_tracked' for r in entry.results) else
            'seen' if entry.results else 'not_applicable',
        actions=([dict(kind='inspect', target=entry.target)] if entry.target else []) +
            [dict(kind='attention', attention_id=o['attention_id'], action=action) for o in attention_preview for action in o['allowed_actions']],
        external=entry.external, as_of=now, next_refresh_at=refresh_at)


def page(relations, *, scope, server_id, principal, now, partition='groups', group_id=None,
         entry_id=None, cursor=None, limit=10, preview=3, check_budget=lambda: None, presentation_version=1):
    if type(presentation_version) is not int or presentation_version not in (1, 2):
        invalid('Invalid Home presentation version.')
    page_limit(limit)
    page_limit(preview)
    if partition not in {'groups', 'children', 'sessions', 'attention', 'results'}:
        invalid('Invalid Home entries partition.')
    if partition == 'groups' and (group_id is not None or entry_id is not None) or partition != 'groups' and group_id is None or partition == 'children' and entry_id is not None or partition in {'sessions', 'attention', 'results'} and entry_id is None:
        invalid('Invalid Home entries parent references.')
    for value in (group_id, entry_id):
        if value is not None:
            identity(value)
    material_revision = revision(relations, check_budget)
    if presentation_version == 2:
        material_revision = digest([2, material_revision])
    tracking_unknown, old_tracking_unknown, unseen_results = False, False, set()
    refresh = instant(now) + timedelta(seconds=15)
    for entry in relations.entries:
        check_budget()
        for occurrence in entry.attention:
            check_budget()
            change = occurrence.get('next_change_at')
            if change and instant(now) < instant(change):
                refresh = min(refresh, instant(change))
        for observation in entry.external:
            check_budget()
            report = observation.get('last_report')
            if report and observation['freshness'] == 'current' and instant(now) < instant(report['valid_until']):
                refresh = min(refresh, instant(report['valid_until']))
        for result in entry.results:
            check_budget()
            if result['view_state'] == 'unseen':
                unseen_results.add(result['id'])
            elif result['view_state'] == 'not_tracked':
                tracking_unknown = True
                if result['created_at'] is None or instant(result['created_at']) < instant(now) - timedelta(hours=24):
                    old_tracking_unknown = True
    exact = relations.total_is_exact and not (scope['include_recent_results'] and old_tracking_unknown)
    for occurrence in relations.server_attention:
        check_budget()
        change = occurrence.get('next_change_at')
        if change and instant(now) < instant(change):
            refresh = min(refresh, instant(change))
    refresh_at = refresh.isoformat(timespec='microseconds').replace('+00:00', 'Z')
    binding = dict(server_id=server_id, principal=principal, scope=scope,
                   partition=partition, group_id=group_id, entry_id=entry_id)
    if presentation_version == 2:
        binding['presentation_version'] = 2
    after = cursor_decode(cursor, binding, material_revision)
    groups = {}
    for entry in relations.entries:
        check_budget()
        matches_agent = (scope.get('agent_id') is None or entry.agent_id == scope['agent_id']
            or entry.activity is not None and scope['agent_id'] in entry.activity['agent_ids']
            or any(s.agent_id == scope['agent_id'] for s in entry.sessions))
        if selected(entry, scope, now) and (presentation_version == 1 or matches_agent):
            groups.setdefault(entry.group_id, []).append(entry)
    for children in groups.values():
        check_budget()
        children.sort(key=entry_key)
    if group_id is not None and group_id not in groups:
        raise OktoNexusError(ErrorCode.NOT_FOUND, 'Home entry group is unavailable in this scope.', {})
    if partition == 'groups':
        values = sorted(groups.items(), key=lambda row: entry_key(row[1][0]))
        keyed = [(entry_key(children[0])[:2] + (key,), (key, children)) for key, children in values]
    elif partition == 'children':
        keyed = [(entry_key(e), e) for e in groups[group_id]]
    else:
        entry = next((e for e in groups[group_id] if e.id == entry_id), None)
        if entry is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Home entry is unavailable in this group.', {})
        if partition == 'sessions':
            keyed = [((0, s.executor_id, s.session_id), s) for s in entry.sessions]
        elif partition == 'attention':
            keyed = [(attention_key(item), item) for item in entry.attention]
        else:
            keyed = [(result_key(item), item) for item in entry.results]
    keyed.sort(key=lambda row: row[0])
    if after is not None and not any(key == after for key, _ in keyed):
        conflict('Home entries cursor ordering anchor is unavailable.')
    remaining = [(key, value) for key, value in keyed if after is None or key > after]
    chosen, more = remaining[:limit], len(remaining) > limit
    items = []
    attention_exact = all(relations.source_status.get(name) == 'ready' for name in ('attention', 'work', 'correlations'))
    results_exact = all(relations.source_status.get(name) == 'ready' for name in ('results', 'work', 'correlations'))
    for _, value in chosen:
        check_budget()
        if partition == 'groups':
            key, children = value
            first = children[0]
            c = first.connection
            context_labels = [value for value in (c.agent_label or 'Agent name unavailable', c.workspace_label, c.host_label) if value] if c else []
            child_binding = dict(binding, partition='children', group_id=key, entry_id=None)
            items.append(dict(id=key, server_id=server_id, executor_id=c.executor_id if c else None,
                workspace_id=first.workspace_id, agent_id=first.agent_id,
                connection={k: getattr(c, k) for k in ('server_id', 'executor_id', 'binding_id', 'workspace_id', 'agent_id')} if c else None,
                label=' · '.join(context_labels)[:160] if c else first.title,
                agent_label=c.agent_label if c else None, workspace_label=c.workspace_label if c else None, host_label=c.host_label if c else None,
                children=[entry_dto(e, binding=binding, revision=material_revision, group_id=key, now=now, refresh_at=refresh_at, preview=preview, sessions_exact=relations.source_status.get('sessions') == 'ready' and relations.source_status.get('correlations') == 'ready', attention_exact=attention_exact, results_exact=results_exact) for e in children[:preview]],
                children_total=len(children) if exact else None,
                has_more_children=len(children)>preview,
                children_cursor=cursor_encode(child_binding, material_revision, list(entry_key(children[preview-1]))) if len(children)>preview else None))
        elif partition == 'children':
            items.append(entry_dto(value, binding=binding, revision=material_revision, group_id=group_id, now=now, refresh_at=refresh_at, preview=preview, sessions_exact=relations.source_status.get('sessions') == 'ready' and relations.source_status.get('correlations') == 'ready', attention_exact=attention_exact, results_exact=results_exact))
        elif partition == 'sessions':
            items.append(session_ref(value))
        else:
            items.append(value)
    check_budget()
    counts, sessions, results = dict(activities=0, external_instances=0, occurrences=0), set(), set()
    for children in groups.values():
        for entry in children:
            check_budget()
            counts['activities'] += entry.kind == 'work'
            counts['external_instances'] += len(entry.external)
            counts['occurrences'] += sum(o['active'] and o['category'] == 'action_required' for o in entry.attention)
            sessions.update((s.server_id, s.executor_id, s.session_id) for s in entry.sessions)
            results.update(r['id'] for r in entry.results)
    counts.update(sessions=len(sessions), results=len(results))
    check_budget()
    value = {'version': 1, 'scope': scope, 'server_id': server_id, 'generated_at': now,
        'snapshot_id': material_revision, 'revision': material_revision, 'partition': partition,
        'group_id': group_id, 'entry_id': entry_id, 'status': 'ready' if exact else 'partial',
        'source_status': relations.source_status, 'items': items, 'total': len(keyed) if exact else None,
        'total_is_exact': exact, 'has_more': more,
        'inventory': dict(connections=dict(value=relations.connection_count,
            total_is_exact=relations.connection_count is not None,
            unit='connections')),
        'coverage': dict(result_tracking='unknown' if relations.source_status.get('attention') != 'ready' else 'partial' if tracking_unknown else 'ready'),
        'next_cursor': cursor_encode(binding, material_revision, list(chosen[-1][0])) if more else None,
        'as_of': now, 'next_refresh_at': refresh_at,
        'server_attention': dict(status='ready' if relations.source_status.get('attention') == 'ready' else 'unavailable',
            items=[o for o in relations.server_attention if o['active']][:3] if partition == 'groups' else [],
            total=sum(o['active'] for o in relations.server_attention) if relations.source_status.get('attention') == 'ready' else None,
            total_is_exact=relations.source_status.get('attention') == 'ready', has_more=sum(o['active'] for o in relations.server_attention)>3),
        'summary': dict({key: dict(value=count if exact else None,
            total_is_exact=exact, unit=key) for key, count in counts.items()},
            unseen_results=dict(value=None if tracking_unknown or relations.source_status.get('attention') != 'ready' else len(unseen_results),
                total_is_exact=not tracking_unknown and relations.source_status.get('attention') == 'ready', unit='results'))}
    if presentation_version == 2:
        value.update(presentation_version=2, presentation_versions=[1, 2])
    return value
