"""Exclusive board columns over one complete, authorized Home entry relation.

The global board revision fences membership and ordering. Related entry pages
retain their own existing relation revision and quick=all scope.
"""
from datetime import timedelta
from typing import Literal, TypedDict

from . import home_entry_pages as entries
from .attention import digest, instant
from .home import invalid


COLUMNS = ('active', 'needs_you', 'results')
BoardColumn = Literal['active', 'needs_you', 'results']


class ColumnPage(TypedDict):
    items: list[dict[str, object]]
    total: int | None
    total_is_exact: bool
    has_more: bool
    next_cursor: str | None


def column_for(entry, now) -> BoardColumn | None:
    if any(o['active'] and o['freshness'] == 'current' and o['resolution'] == 'open'
           and o['category'] == 'action_required' and o['allowed_actions'] for o in entry.attention):
        return 'needs_you'
    # Persisted context and external reports never assert productive execution
    # or a canonical successful result.
    if entry.kind == 'attention':
        return 'active' if any(o['active'] for o in entry.attention) else None
    if entry.kind in ('session', 'connection', 'external'):
        return 'active'
    if entry.display_state not in entries.TERMINAL:
        return 'active'
    retained = any(r['view_state'] in ('unseen', 'not_tracked') or not r['created_at']
                   or instant(r['created_at']) >= instant(now) - timedelta(hours=24)
                   for r in entry.results)
    if retained:
        return 'results'
    # Terminal work without a separate result is still an outcome, not running.
    timestamp = entry.activity['last_activity_at'] if entry.activity else None
    if not entry.results and timestamp and instant(timestamp) >= instant(now) - timedelta(hours=24):
        return 'results'
    return None


def summary_for(columns, *, exact, attention_ready, check_budget):
    counts = dict(activities=0, external_instances=0)
    sessions, results, unseen, occurrences = set(), set(), set(), set()
    tracking_unknown = False
    for values in columns.values():
        for entry in values:
            check_budget()
            counts['activities'] += entry.kind == 'work'
            counts['external_instances'] += len(entry.external)
            for session in entry.sessions:
                check_budget()
                sessions.add((session.server_id, session.executor_id, session.session_id))
            for occurrence in entry.attention:
                check_budget()
                if occurrence['active'] and occurrence['category'] == 'action_required':
                    occurrences.add(occurrence['attention_id'])
            for result in entry.results:
                check_budget()
                results.add(result['id'])
                if result['view_state'] == 'unseen':
                    unseen.add(result['id'])
                elif result['view_state'] == 'not_tracked':
                    tracking_unknown = True
    counts.update(sessions=len(sessions), results=len(results), occurrences=len(occurrences))
    summary = {key: dict(value=value if exact else None, total_is_exact=exact, unit=key)
               for key, value in counts.items()}
    unseen_exact = exact and attention_ready and not tracking_unknown
    summary['unseen_results'] = dict(value=len(unseen) if unseen_exact else None,
        total_is_exact=unseen_exact, unit='results')
    return summary, tracking_unknown


def unavailable(value, column=None):
    value = dict(value, partition='board_column' if column else 'board', entry_revision=None)
    empty = dict(items=[], total=None, total_is_exact=False, has_more=False, next_cursor=None)
    if column:
        value.update(column=column, **empty)
    else:
        for key in ('items', 'total', 'total_is_exact', 'has_more', 'next_cursor'):
            value.pop(key, None)
        value['columns'] = {name: dict(empty) for name in COLUMNS}
    return value


def page(relations, *, scope, server_id, principal, now, column=None, cursor=None,
         limit=10, preview=3, check_budget=lambda: None):
    entries.page_limit(limit)
    entries.page_limit(preview)
    if column is not None and column not in COLUMNS:
        invalid('Invalid Home board column.')
    if cursor is not None and column is None:
        invalid('A Home board cursor requires its exact column.')
    # This is a serializer over the SAME relation, not a second source read.
    base = entries.page(relations, scope=scope, server_id=server_id, principal=principal,
        now=now, limit=1, preview=1, check_budget=check_budget)
    entry_revision = base['revision']
    columns = {name: [] for name in COLUMNS}
    old_unknown = False
    refresh = instant(base['next_refresh_at'])
    for entry in relations.entries:
        check_budget()
        if not entries.selected(entry, scope, now):
            continue
        name = column_for(entry, now)
        if name is not None:
            columns[name].append(entry)
        for result in entry.results:
            check_budget()
            stamp = result['created_at']
            expiry = instant(stamp) + timedelta(hours=24) if stamp else None
            if result['view_state'] == 'not_tracked' and (expiry is None or expiry < instant(now)):
                old_unknown = True
            if expiry and expiry > instant(now) and result['view_state'] == 'seen':
                refresh = min(refresh, expiry)
    for values in columns.values():
        values.sort(key=entries.entry_key)
    revision = digest([entry_revision, {name: [e.id for e in values] for name, values in columns.items()}])
    exact = relations.total_is_exact and not old_unknown
    base.update(partition='board_column' if column else 'board', revision=revision,
        snapshot_id=revision, entry_revision=entry_revision, status='ready' if exact else 'partial',
        next_refresh_at=refresh.isoformat(timespec='microseconds').replace('+00:00', 'Z'))
    for key in ('items', 'total', 'total_is_exact', 'has_more', 'next_cursor', 'group_id', 'entry_id'):
        base.pop(key, None)
    base['summary'], tracking_unknown = summary_for(columns, exact=exact,
        attention_ready=relations.source_status.get('attention') == 'ready', check_budget=check_budget)
    base['coverage'] = dict(result_tracking='unknown' if relations.source_status.get('attention') != 'ready'
        else 'partial' if tracking_unknown else 'ready')
    result = {}
    for name in (COLUMNS if column is None else (column,)):
        check_budget()
        binding = dict(server_id=server_id, principal=principal, scope=scope,
            partition='board:' + name, group_id=None, entry_id=None)
        after = entries.cursor_decode(cursor, binding, revision)
        keyed = [(entries.entry_key(e), e) for e in columns[name]]
        if after is not None and not any(key == after for key, _ in keyed):
            entries.conflict('Home board cursor ordering anchor is unavailable.')
        remaining = [(key, e) for key, e in keyed if after is None or key > after]
        chosen, more = remaining[:limit], len(remaining) > limit
        values = []
        for _, entry in chosen:
            check_budget()
            dto = entries.entry_dto(entry, binding=dict(binding, partition='groups'),
                revision=entry_revision, group_id=entry.group_id, now=now,
                refresh_at=base['next_refresh_at'], preview=preview,
                sessions_exact=all(relations.source_status.get(k) == 'ready' for k in ('sessions', 'correlations')),
                attention_exact=all(relations.source_status.get(k) == 'ready' for k in ('attention', 'work', 'correlations')),
                results_exact=all(relations.source_status.get(k) == 'ready' for k in ('results', 'work', 'correlations')))
            dto.update(group_id=entry.group_id, entry_revision=entry_revision)
            values.append(dto)
        result[name] = dict(items=values, total=len(keyed) if exact else None,
            total_is_exact=exact, has_more=more,
            next_cursor=entries.cursor_encode(binding, revision, list(chosen[-1][0])) if more else None)
    if column is None:
        base['columns'] = result
    else:
        base.update(column=column, **result[column])
    check_budget()
    return base
