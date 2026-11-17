"""One registered connection card per exclusive column, never guessed identity."""
from dataclasses import asdict, replace
from datetime import timedelta

from ..errors import ErrorCode, OktoNexusError
from . import home_board as board
from . import home_entry_pages as entries
from . import home_harness_blocking
from .attention import canonical, digest, instant
from .home import invalid
from .home_entries import passive_record
from .home_operational_status import action_kind, count


def connection_key(c):
    return tuple(getattr(c, name) for name in
                 ('server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id'))


def context_record(c):
    entry = passive_record(c)
    entry.connection = c
    return entry


def card_column(children):
    if any(name == 'needs_you' for name, _ in children):
        return 'needs_you'
    if any(name == 'active' and e.kind in ('work', 'attention') for name, e in children):
        return 'active'
    if any(name == 'results' for name, _ in children):
        return 'results'
    return 'active'  # Registered/passive context, never a RUNNING assertion.


def child_key(pair):
    name, entry = pair
    return ({'needs_you': 0, 'active': 1, 'results': 2}[name], entries.entry_key(entry)[1], entry.id)


def unavailable(value, *, partition, column=None, card_id=None, presentation_version=1):
    value = board.unavailable(value, column if partition == 'column' else None)
    value['partition'] = {'root': 'harness_board', 'column': 'harness_board_column',
                          'children': 'harness_children', 'unlinked': 'harness_unlinked',
                          'requests': 'harness_requests', 'sessions': 'harness_sessions'}[partition]
    empty = dict(items=[], total=None, total_is_exact=False, has_more=False, next_cursor=None)
    value['coverage']['harness_linkage'] = 'unknown'
    value['coverage']['blocking'] = 'unknown'
    value['inventory']['registered_harnesses'] = dict(value=None, total_is_exact=False, unit='harnesses')
    if partition == 'root':
        value['unlinked'] = dict(empty)
    elif partition in ('children', 'unlinked', 'requests', 'sessions'):
        value.pop('columns', None)
        value.update(**empty)
        if partition in ('children', 'requests', 'sessions'):
            value['card_id'] = card_id
    if presentation_version == 2:
        value.update(presentation_version=2, presentation_versions=[1, 2],
            operational_summary={name: count(None, False) for name in (
                'connected', 'working', 'idle', 'queued', 'unconfirmed', 'disconnected',
                'blocked_harnesses', 'pending_actions', 'visible_notifications', 'resume_confirmations')})
    return value


def page(relations, *, scope, server_id, principal, now, partition='root', column=None,
         card_id=None, cursor=None, limit=10, preview=3, check_budget=lambda: None, presentation_version=1):
    if type(presentation_version) is not int or presentation_version not in (1, 2):
        invalid('Invalid Home presentation version.')
    operational = presentation_version == 2
    entries.page_limit(limit)
    entries.page_limit(preview)
    if partition not in (('root', 'column', 'children', 'unlinked', 'requests', 'sessions') if operational else ('root', 'column', 'children', 'unlinked')):
        invalid('Invalid harness board partition.')
    if (partition == 'column') != (column in board.COLUMNS) or partition != 'column' and column is not None:
        invalid('Invalid harness board column.')
    if (partition in ('children', 'requests', 'sessions')) != (card_id is not None):
        invalid('Invalid harness board card reference.')
    if card_id is not None:
        entries.identity(card_id)
    if partition == 'root' and cursor is not None:
        invalid('A harness board cursor requires an exact partition.')
    base_options = {'presentation_version': 2} if operational else {}
    base = entries.metadata(relations, scope=scope, server_id=server_id,
        now=now, check_budget=check_budget, **base_options)
    entry_revision = base['revision']
    registry = {connection_key(c): c for c in relations.connections or ()}
    groups = {key: [] for key in registry}
    all_sessions = {}
    for entry in relations.entries:
        check_budget()
        for session in entry.sessions:
            check_budget()
            all_sessions[(session.server_id, session.executor_id, session.workspace_id, session.session_id)] = session
    retained, unlinked, links, complete_links = {}, [], {}, {}
    old_unknown, refresh = False, instant(base['next_refresh_at'])
    for entry in relations.entries:
        check_budget()
        presentation_scope = {key: value for key, value in scope.items() if key not in ('harness', 'host')}
        name = board.column_for(entry, now)
        proven = {connection_key(c) for c in entry.registered_connections if connection_key(c) in registry}
        if entry.kind == 'connection' and entry.connection is not None and connection_key(entry.connection) in registry:
            proven.add(connection_key(entry.connection))
        for session in entry.sessions:
            check_budget()
            if connection_key(session) in registry:
                proven.add(connection_key(session))
        # External association requires the persisted canonical session tuple,
        # resolved against this same authorized complete session relation.
        for observation in entry.external:
            check_budget()
            ref = observation.get('canonical_session_ref')
            session = all_sessions.get((ref['server_id'], ref['executor_id'], entry.workspace_id, ref['session_id'])) if ref else None
            if session is not None and connection_key(session) in registry:
                proven.add(connection_key(session))
        complete_links[entry.id] = set(proven)
        matches_agent = (scope.get('agent_id') is None or entry.agent_id == scope['agent_id']
            or entry.activity is not None and scope['agent_id'] in entry.activity['agent_ids']
            or any(s.agent_id == scope['agent_id'] for s in entry.sessions))
        if (operational and not matches_agent) or not entries.selected(entry, presentation_scope, now) or name is None:
            continue
        proven = {key for key in proven if scope.get('harness') in (None, registry[key].harness_id)
                  and scope.get('host') in (None, registry[key].executor_id)}
        if not proven and (scope.get('harness') is not None or scope.get('host') is not None):
            continue
        retained[entry.id] = entry
        links[entry.id] = proven
        if proven:
            for key in proven:
                groups[key].append((name, entry))
        else:
            unlinked.append((name, entry))
        for result in entry.results:
            check_budget()
            expiry = instant(result['created_at']) + timedelta(hours=24) if result['created_at'] else None
            if result['view_state'] == 'not_tracked' and (expiry is None or expiry < instant(now)):
                old_unknown = True
            if expiry and expiry > instant(now) and result['view_state'] == 'seen':
                refresh = min(refresh, expiry)
    cards, columns = {}, {name: [] for name in board.COLUMNS}
    for key, children in groups.items():
        check_budget()
        c = registry[key]
        context = context_record(c)
        if scope.get('harness') not in (None, c.harness_id) or scope.get('host') not in (None, c.executor_id):
            continue
        if scope.get('agent_id') not in (None, c.agent_id) and not children:
            continue
        if scope.get('state') not in (None, 'all') and not children:
            continue
        children.sort(key=child_key)
        group_id = context.group_id
        name = card_column(children)
        # Passive context never creates a second card nor masks Results.
        keyset = child_key(children[0])[:2] + (group_id,) if children else (3, '99999999999999999999', group_id)
        cards[group_id] = (c, children, keyset)
        columns[name].append(group_id)
    reducer = home_harness_blocking.project_v2 if operational else home_harness_blocking.project
    states, own_request_keys, waiting = reducer(relations, registry,
        now=now, check_budget=check_budget)
    operation_keys = {}
    for row in relations.harness_blocking or ():
        check_budget()
        if row['family'] == 'operation':
            operation_keys[(row['server_id'], row['executor_id'], row['operation_id'], row['session_id'], row['workspace_id'], row['agent_id'])] = tuple(row.get(k) for k in home_harness_blocking.FIELDS)
    requests, deliveries = {}, {}
    key_to_card = {connection_key(c): identifier for identifier, (c, _, _) in cards.items()}
    for entry in relations.entries:
        check_budget()
        if not operational and entry.id not in retained and not any(o['attention_id'] in waiting for o in entry.attention):
            continue
        for occurrence in entry.attention:
            check_budget()
            human = occurrence['category'] == 'action_required' and occurrence['freshness'] == 'current' and occurrence['resolution'] == 'open' and occurrence['allowed_actions']
            if human:
                keys = own_request_keys.get(occurrence['attention_id'])
                if keys is None and occurrence.get('operation_id'):
                    key = operation_keys.get((server_id, occurrence.get('executor_id'), occurrence['operation_id'],
                        occurrence.get('session_id'), occurrence['workspace_id'], occurrence['agent_id']))
                    keys = {key} if key in registry else set()
                if keys is None:
                    # A handoff/coordination action may reference shared work;
                    # this is provenance only, never proof of a native pause.
                    keys = (complete_links if operational else links).get(entry.id, set()) if occurrence['source_type'] != 'execution_native_request' else set()
                if operational and entry.id not in retained and not any(key in key_to_card for key in keys):
                    continue
                requests[occurrence['attention_id']] = (entry, occurrence, set(keys))
            if occurrence['kind'] == 'external_completion_unseen' and occurrence['active']:
                deliveries['reported:' + occurrence['attention_id']] = (entry, None, occurrence, set())
        if entry.id not in retained:
            continue
        for result in entry.results:
            check_budget()
            if result['view_state'] == 'seen' and result['created_at'] and instant(result['created_at']) < instant(now) - timedelta(hours=24):
                continue
            deliveries['canonical:' + result['id']] = (entry, result, None, links.get(entry.id, set()))
    columns = {name: [] for name in board.COLUMNS}
    for identifier, (c, _, keyset) in cards.items():
        state = states[connection_key(c)]
        needs = state['blocks_harness'] is True or operational and state['placement_reason'] == 'awaiting_native_confirmation'
        columns['needs_you' if needs else 'active'].append((keyset, ('harness', identifier)))
    for identifier, (_, occurrence, keys) in requests.items():
        check_budget()
        incorporated = (len(keys) == 1 if operational else True) and any(key in key_to_card and states[key]['blocks_harness'] is True for key in keys)
        if occurrence['active'] and not incorporated:
            columns['needs_you'].append((entries.attention_key(occurrence), ('request', identifier)))
    for identifier, (_, result, report, _) in deliveries.items():
        stamp = result['created_at'] if result else report['last_changed_at']
        columns['results'].append(((0, entries._newest(stamp), identifier), ('delivery', identifier)))
    requests_by_connection, sessions_by_connection, native_requests_by_connection = {}, {}, {}
    for identifier, (_, o, keys) in requests.items():
        check_budget()
        if len(keys) == 1:
            requests_by_connection.setdefault(next(iter(keys)), []).append((entries.attention_key(o), identifier))
    for values in requests_by_connection.values():
        values.sort()
    for s in relations.operational_sessions or ():
        check_budget()
        key = tuple(getattr(s, name) for name in home_harness_blocking.FIELDS)
        sessions_by_connection.setdefault(key, []).append(((0, s.session_id, s.session_id), s))
    for values in sessions_by_connection.values():
        values.sort(key=lambda pair: pair[0])
    for rid, keys in own_request_keys.items():
        check_budget()
        for key in keys:
            native_requests_by_connection.setdefault(key, set()).add(rid)
    for values in columns.values():
        values.sort(key=lambda pair: pair[0])
    unlinked.sort(key=child_key)
    if operational:
        # Runtime evidence timestamps/renewals are diagnostic. Only their
        # semantic classification and exact decision refs invalidate pages.
        def semantic_state(state):
            value = dict(state)
            value['operational_status'] = dict(value['operational_status'], as_of=None)
            return value
        session_membership = sorted((s.server_id, s.executor_id, s.binding_id, s.workspace_id,
            s.workspace_binding_id, s.agent_id, s.session_id, s.stream_epoch, s.owner_generation,
            s.lifecycle_state, s.title, s.workspace_label) for s in relations.operational_sessions or ())
        revision = digest([2, entry_revision, columns, session_membership, {canonical(key): semantic_state(value)
            for key, value in sorted(states.items())},
            {identifier: [e.id for _, e in children] for identifier, (_, children, _) in sorted(cards.items())},
            [e.id for _, e in unlinked]])
        for fact in relations.operational_sessions or ():
            check_budget()
            if fact.control_current and fact.valid_until and instant(fact.valid_until) > instant(now):
                refresh = min(refresh, instant(fact.valid_until))
        for row in relations.harness_blocking or ():
            if row['family'] == 'request' and row['state'] == 'PENDING' and instant(row['expires_at']) > instant(now):
                refresh = min(refresh, instant(row['expires_at']))
    else:
        revision = digest([entry_revision, columns,
            None if relations.harness_blocking is None else sorted(relations.harness_blocking, key=canonical),
            {identifier: [e.id for _, e in children] for identifier, (_, children, _) in sorted(cards.items())},
            [e.id for _, e in unlinked]])
    exact = relations.total_is_exact and relations.connections is not None and not old_unknown
    base.update(partition={'root': 'harness_board', 'column': 'harness_board_column',
        'children': 'harness_children', 'unlinked': 'harness_unlinked',
        'requests': 'harness_requests', 'sessions': 'harness_sessions'}[partition],
        revision=revision, snapshot_id=revision, entry_revision=entry_revision,
        status='ready' if exact else 'partial',
        next_refresh_at=refresh.isoformat(timespec='microseconds').replace('+00:00', 'Z'))
    base['inventory']['registered_harnesses'] = dict(value=len(cards) if exact else None,
        total_is_exact=exact, unit='harnesses')
    for name in ('items', 'total', 'total_is_exact', 'has_more', 'next_cursor', 'group_id', 'entry_id'):
        base.pop(name, None)
    # Shared work contributes once globally, even when referenced by two cards.
    base['summary'], tracking_unknown = board.summary_for({'retained': list(retained.values())},
        exact=exact, attention_ready=relations.source_status.get('attention') == 'ready', check_budget=check_budget)
    # R3 Results is a delivery feed: reported completions are explicitly typed
    # reported, and must not silently vanish from its visible aggregate.
    delivery_unseen, delivery_tracking_unknown = set(), False
    canonical_deliveries = 0
    for identifier, (_, result, report, _) in deliveries.items():
        check_budget()
        if result:
            canonical_deliveries += 1
            if result['view_state'] == 'unseen':
                delivery_unseen.add(identifier)
            elif result['view_state'] == 'not_tracked':
                delivery_tracking_unknown = True
        elif report.get('seen_state') is None:
            delivery_tracking_unknown = True
        elif not report['seen_state']['seen']:
            delivery_unseen.add(identifier)
    base['summary']['results'] = dict(value=len(deliveries) if exact else None, total_is_exact=exact, unit='results')
    base['summary']['occurrences'] = dict(value=len(requests) if exact else None, total_is_exact=exact, unit='occurrences')
    unseen_exact = exact and not delivery_tracking_unknown and relations.source_status.get('attention') == 'ready'
    base['summary']['unseen_results'] = dict(value=len(delivery_unseen) if unseen_exact else None,
        total_is_exact=unseen_exact, unit='results')
    base['delivery_counts'] = dict(canonical=canonical_deliveries if exact else None,
        reported=len(deliveries)-canonical_deliveries if exact else None, total_is_exact=exact)
    tracking_unknown = tracking_unknown or delivery_tracking_unknown
    base['coverage'] = dict(result_tracking='unknown' if relations.source_status.get('attention') != 'ready'
        else 'partial' if tracking_unknown else 'ready',
        harness_linkage='ready' if relations.connections is not None and relations.source_status.get('correlations') == 'ready' else 'unknown',
        blocking='ready' if relations.harness_blocking is not None else 'unknown')
    if relations.harness_blocking is None:
        base['status'] = 'partial'
    if operational:
        base['presentation_version'] = 2
        base['presentation_versions'] = [1, 2]
        selected_states = [state['operational_status'] for state in states.values()]
        status_exact = (relations.operational_sessions is not None and relations.harness_blocking is not None
            and relations.connections is not None and all(relations.source_status.get(name) == 'ready'
                for name in ('connections', 'sessions', 'correlations')))
        action_exact = relations.source_status.get('attention') == 'ready'
        base['operational_summary'] = {name: count(sum(s[field] == value for s in selected_states), status_exact)
            for name, field, value in (('connected', 'connection', 'connected'), ('working', 'activity', 'working'),
                ('idle', 'activity', 'idle'), ('queued', 'activity', 'queued'), ('unconfirmed', 'activity', 'unknown'),
                ('disconnected', 'connection', 'disconnected'), ('blocked_harnesses', 'blocking', 'full'))}
        for name in ('working', 'idle', 'queued', 'blocked_harnesses'):
            if any(s['activity'] == 'unknown' or s['blocking'] == 'unknown' for s in selected_states):
                base['operational_summary'][name] = count(None, False)
        for name in ('connected', 'disconnected'):
            if any(s['connection'] in ('unknown', 'registered') for s in selected_states):
                base['operational_summary'][name] = count(None, False)
        all_actions = {o['attention_id']: o for e in relations.entries for o in e.attention
            if o['category'] == 'action_required' and o['freshness'] == 'current'
            and o['resolution'] == 'open' and o['allowed_actions']}
        base['operational_summary'].update(pending_actions=count(len(all_actions), action_exact),
            visible_notifications=count(sum(bool(o['active']) for o in all_actions.values()), action_exact),
            resume_confirmations=count(sum(s['awaiting_native_confirmation'] for s in selected_states), status_exact))

    def binding(kind, parent=None):
        value = {'server_id': server_id, 'principal': principal, 'scope': scope,
            'partition': ('harness:v2:' if operational else 'harness:') + kind, 'group_id': parent, 'entry_id': None}
        if operational:
            value['presentation_version'] = 2
        return value

    def slice_page(keyed, fence, *, bound=limit, after_cursor=None, render=lambda value: value, exactness=None):
        check_budget()
        after = entries.cursor_decode(after_cursor, fence, revision)
        if after is not None and not any(key == after for key, _ in keyed):
            entries.conflict('Harness board cursor ordering anchor is unavailable.')
        remaining = [(key, value) for key, value in keyed if after is None or key > after]
        chosen, more = remaining[:bound], len(remaining) > bound
        known = exact if exactness is None else exactness
        return {'items': [render(value) for _, value in chosen], 'total': len(keyed) if known else None,
            'total_is_exact': known, 'has_more': more,
            'next_cursor': entries.cursor_encode(fence, revision, list(chosen[-1][0])) if more else None}

    def child_dto(pair):
        _, entry = pair
        check_budget()
        value = entries.entry_dto(entry, binding=binding('detail'), revision=entry_revision,
            group_id=entry.group_id, now=now, refresh_at=base['next_refresh_at'], preview=preview,
            sessions_exact=all(relations.source_status.get(k) == 'ready' for k in ('sessions', 'correlations')),
            attention_exact=all(relations.source_status.get(k) == 'ready' for k in ('attention', 'work', 'correlations')),
            results_exact=all(relations.source_status.get(k) == 'ready' for k in ('results', 'work', 'correlations')))
        value.update(group_id=entry.group_id, entry_revision=entry_revision, shared_reference=len(links.get(entry.id, ())) > 1)
        return value

    def card_dto(identifier):
        c, children, _ = cards[identifier]
        preview_page = slice_page([(child_key(pair), pair) for pair in children], binding('children', identifier),
            bound=preview, render=child_dto)
        own_requests = native_requests_by_connection.get(connection_key(c), set())
        scoped_children = [replace(e, attention=[o for o in e.attention
            if o['source_type'] != 'execution_native_request' or o['attention_id'] in own_requests]) for _, e in children]
        summary, _ = board.summary_for({'children': scoped_children}, exact=exact,
            attention_ready=relations.source_status.get('attention') == 'ready', check_budget=check_budget)
        events, event_counts = event_preview(children, entry_revision=entry_revision,
            links=links, now=now, check_budget=check_budget, own_requests=own_requests)
        by_id = {entry.id: pair for pair in children for entry in (pair[1],)}
        event_items = [dict(event, entry=child_dto(by_id[event['entry_id']])) for event in events[:preview]]
        state = states[connection_key(c)]
        blockers = [request_dto(request_id) for request_id in state['blocking_request_ids'] if request_id in requests]
        value = dict(id=identifier, kind='harness', group_id=identifier, connection=asdict(c),
            target=context_record(c).target, context_state='registered',
            reconnect_available=False, reconnect_reason='Individual reconnection is not supported by the current canonical API.',
            children=preview_page['items'], children_total=preview_page['total'],
            has_more_children=preview_page['has_more'], children_cursor=preview_page['next_cursor'], summary=summary,
            events_preview=event_items, events_total=len(events) if exact else None,
            has_more_events=len(events)>preview,
            events_summary={name: value if exact else None for name, value in event_counts.items()},
            **{key: val for key, val in state.items() if not key.startswith('_')}, blocking_requests=blockers)
        if operational:
            own_page = request_page(identifier, bound=preview)
            status = dict(value['operational_status'])
            own = [requests[rid][1] for _, rid in requests_by_connection.get(connection_key(c), ())]
            action_exact = relations.source_status.get('attention') == 'ready'
            status.update(pending_actions=count(len(own), action_exact),
                pending_by_kind={kind: count(sum(action_kind(o) == kind for o in own), action_exact)
                    for kind in ('question', 'approval', 'decision', 'verification')},
                pending_request_ids=[item['request']['attention_id'] for item in own_page['items']],
                has_more_pending_requests=own_page['has_more'], pending_requests_cursor=own_page['next_cursor'])
            value['operational_status'] = status
            value['requests_preview'] = own_page['items']
            value['blocking_request_ids'] = value['blocking_request_ids'][:preview]
            value['blocking_requests'] = blockers[:preview]
            session_page = sessions_page(identifier, bound=preview)
            value.update(sessions=session_page['items'], sessions_total=session_page['total'],
                has_more_sessions=session_page['has_more'], sessions_cursor=session_page['next_cursor'])
        return value

    def references(keys):
        return [dict(card_id=key_to_card[key], connection=asdict(registry[key])) for key in sorted(keys) if key in key_to_card]

    def request_dto(identifier):
        entry, occurrence, keys = requests[identifier]
        own_states = [states[key]['blocks_harness'] for key in keys if key in key_to_card]
        blocks = True if identifier in waiting and any(value is True for value in own_states) else False if own_states and all(value is False for value in own_states) else None
        value = {'kind': 'request', 'id': 'home_request_' + identifier, 'request': occurrence,
            'entry': child_dto(('needs_you', entry)), 'harness_refs': references(keys),
            'blocks_harness': blocks, 'notification_visible': bool(occurrence['active'])}
        if operational:
            session_proofs = [states[key].get('_session_blocks', {}).get(identifier) for key in keys if key in states]
            value.update(blocks_session=session_proofs[0] if len(session_proofs) == 1 else None, action_kind=action_kind(occurrence))
        return value

    def delivery_dto(identifier):
        entry, result, report, keys = deliveries[identifier]
        value = {'kind': 'delivery', 'id': 'home_delivery_' + identifier, 'result': result, 'report': report,
            'entry': child_dto(('results', entry)), 'harness_refs': references(keys),
            'completion_evidence': 'canonical' if result else 'reported'}
        if operational:
            from .home_delivery_semantics import reported_semantics
            value['delivery_semantics'] = result.get('delivery_semantics') if result else reported_semantics(report)
        return value

    def request_page(identifier, *, bound=limit, after_cursor=None):
        c = cards[identifier][0]
        values = requests_by_connection.get(connection_key(c), [])
        return slice_page(values, binding('requests', identifier), bound=bound, after_cursor=after_cursor, render=request_dto,
            exactness=relations.source_status.get('attention') == 'ready' and relations.harness_blocking is not None
                and relations.source_status.get('correlations') == 'ready')

    def sessions_page(identifier, *, bound=limit, after_cursor=None):
        c = cards[identifier][0]
        values = sessions_by_connection.get(connection_key(c), [])
        value = slice_page(values, binding('sessions', identifier), bound=bound, after_cursor=after_cursor,
            render=entries.session_ref,
            exactness=relations.operational_sessions is not None)
        if relations.operational_sessions is None:
            value.update(total=None, total_is_exact=False)
        return value

    def item_dto(item):
        kind, identifier = item
        return card_dto(identifier) if kind == 'harness' else request_dto(identifier) if kind == 'request' else delivery_dto(identifier)

    if partition in ('requests', 'sessions'):
        if card_id not in cards:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Harness card is unavailable in this scope.', {})
        loader = request_page if partition == 'requests' else sessions_page
        base.update(card_id=card_id, **loader(card_id, after_cursor=cursor))
    elif partition == 'children':
        if card_id not in cards:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Harness card is unavailable in this scope.', {})
        children = cards[card_id][1]
        base.update(card_id=card_id, **slice_page([(child_key(pair), pair) for pair in children],
            binding('children', card_id), after_cursor=cursor, render=child_dto))
    elif partition == 'unlinked':
        base.update(**slice_page([(child_key(pair), pair) for pair in unlinked],
            binding('unlinked'), after_cursor=cursor, render=child_dto))
    else:
        slices = {name: slice_page(columns[name],
            binding('column:' + name), after_cursor=cursor if partition == 'column' else None, render=item_dto)
            for name in ((column,) if partition == 'column' else board.COLUMNS)}
        if partition == 'column':
            base.update(column=column, **slices[column])
        else:
            base.update(columns=slices, unlinked=slice_page([(child_key(pair), pair) for pair in unlinked],
                binding('unlinked'), bound=preview, render=child_dto))
    check_budget()
    return base


def event_preview(children, *, entry_revision, links, now, check_budget, own_requests=None):
    """Bounded output only; candidates cover every retained child relationship."""
    candidates = {}
    counts = dict(attention=0, results=0, work=0, sessions=0, external=0)
    for _, entry in children:
        check_budget()
        common = dict(entry_id=entry.id, group_id=entry.group_id, entry_revision=entry_revision,
            target=entry.target, title=entry.title, display_state=entry.display_state,
            evidence=entry.evidence, shared_reference=len(links.get(entry.id, ())) > 1)
        result_attention = {r['attention']['attention_id'] for r in entry.results if r.get('attention')}
        result_ids = {r['id'] for r in entry.results}
        for occurrence in entry.attention:
            check_budget()
            if occurrence['source_type'] == 'execution_native_request' and own_requests is not None and occurrence['attention_id'] not in own_requests:
                continue
            if not occurrence['active']:
                continue
            if occurrence['category'] == 'watch' and (occurrence['attention_id'] in result_attention
                    or occurrence.get('result_id') in result_ids):
                continue
            human = occurrence['category'] == 'action_required' and occurrence['freshness'] == 'current' and bool(occurrence['allowed_actions'])
            identifier = 'attention:' + occurrence['attention_id']
            event = dict(common, id=identifier, kind='attention', occurred_at=occurrence['last_changed_at'], attention=occurrence)
            candidates[identifier] = ((0 if human else 1, entries._newest(event['occurred_at']), identifier), event)
        for result in entry.results:
            check_budget()
            identifier = 'result:' + result['id']
            event = dict(common, id=identifier, kind='result', occurred_at=result['created_at'], result=result, target=result['detail_target'])
            candidates[identifier] = ((3, entries._newest(event['occurred_at']), identifier), event)
        if entry.kind in ('work', 'session', 'external'):
            identifier = entry.kind + ':' + entry.id
            # A delivered terminal work with a result is one useful signal.
            if entry.kind == 'work' and entry.results and entry.display_state in entries.TERMINAL:
                continue
            stamp = entry.activity['last_activity_at'] if entry.activity else None
            event = dict(common, id=identifier, kind=entry.kind, occurred_at=stamp)
            candidates[identifier] = ((2 if entry.kind == 'work' else 4, entries._newest(stamp), identifier), event)
    events = [event for _, event in sorted(candidates.values(), key=lambda row: row[0])]
    for event in events:
        counts[{'result': 'results', 'session': 'sessions'}.get(event['kind'], event['kind'])] += 1
    return events, counts
