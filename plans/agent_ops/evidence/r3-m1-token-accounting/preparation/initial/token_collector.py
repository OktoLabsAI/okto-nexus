"""Pure campaign accounting over the existing canonical event-page contract.

No I/O, clock, native calls, credential reads or dispatch. The controller must
atomically persist each returned state before any productive effect. Observed
usage is not a billing guarantee or an atomically enforced native hard cap.
"""
from copy import deepcopy
import hashlib
import json

IDS = ('server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id',
       'workspace_binding_id', 'session_id')
PRE_SCOPE = IDS[:-1]  # TerminalWork.binding/checkpoint: available before runtime.start.
REVISIONS = ('session_owner_generation', 'authorization_revision',
             'configuration_revision', 'binding_revision', 'credential_epoch')
COUNTERS = ('totalTokens', 'inputTokens', 'cachedInputTokens', 'outputTokens', 'reasoningOutputTokens')
MAX_INT = 2**63 - 1
MAX_SEQUENCE = 2**53 - 1


class Invalid(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Invalid(reason)


def identifier(value):
    require(type(value) is str and 1 <= len(value) <= 160 and value.isprintable(), 'IDENTIFIER_INVALID')
    return value


def number(value, maximum=MAX_INT):
    require(type(value) is int and 0 <= value <= maximum, 'COUNTER_INVALID')
    return value


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def initial_state():
    return {'version': 1, 'revision': 0, 'stop_at': 100000, 'tolerance': 700000, 'max_requests': 6,
            'streams': {}, 'threads': {}, 'turns': {}, 'requests': {},
            'current_request': None, 'faults': []}


def finish(before, after):
    after['revision'] = before['revision']
    if after != before:
        after['revision'] += 1
    return after


def fault(state, reason):
    changed = deepcopy(state)
    if reason not in changed['faults']:
        changed['faults'].append(reason)
        changed['faults'].sort()
    return finish(state, changed)


def stream_id(scope, epoch):
    return encoded([scope['server_id'], scope['executor_id'], scope['session_id'], epoch])


def enroll(state, *, scope, epoch, native_thread_id, baseline_total, baseline_basis):
    """Explicit baseline from fresh-open or retained pre-campaign evidence.

    The collector cannot prove freshness from a zero counter or a successful
    open receipt. baseline_basis is supplied provenance, not a generated proof.
    A same-thread epoch/session handover preserves its existing high-water.
    """
    try:
        require(type(scope) is dict and set(scope) == set(IDS + REVISIONS), 'SCOPE_INVALID')
        for key in IDS:
            identifier(scope[key])
        for key in REVISIONS:
            number(scope[key])
        identifier(epoch)
        identifier(native_thread_id)
        number(baseline_total)
        require(baseline_basis in ('confirmed_fresh_thread', 'retained_pre_campaign_usage'), 'BASELINE_REQUIRED')
        require(baseline_basis != 'confirmed_fresh_thread' or baseline_total == 0, 'FRESH_BASELINE_NOT_ZERO')
        key = stream_id(scope, epoch)
        thread = encoded([scope['server_id'], scope['executor_id'], native_thread_id])
        out = deepcopy(state)
        if key in out['streams']:
            old = out['streams'][key]
            require(old['scope'] == scope and old['thread'] == thread, 'STREAM_REBINDING')
            require(out['threads'][thread]['baseline'] == baseline_total, 'BASELINE_CHANGED')
            return out
        if thread in out['threads']:
            current = out['threads'][thread]
            require(current['baseline'] == baseline_total, 'BASELINE_CHANGED')
            owner = out['streams'][current['owner_stream']]
            require(owner['page_seen'] and not owner['gap'] and owner['cursor'] == owner['watermark'], 'HANDOVER_NOT_CAUGHT_UP')
            require(not any(t['thread'] == thread and not (t['started'] and t['terminal'] and t['usage_seen'])
                            for t in out['turns'].values()), 'HANDOVER_TURN_UNSETTLED')
            require(out['current_request'] is None, 'HANDOVER_REQUEST_UNSETTLED')
            owner['retired'] = True
            current['owner_stream'] = key
        else:
            out['threads'][thread] = {'native_thread_id': native_thread_id,
                'baseline': baseline_total, 'baseline_basis': baseline_basis,
                'high_water': baseline_total, 'components': None, 'owner_stream': key}
        out['streams'][key] = {'scope': deepcopy(scope), 'epoch': epoch, 'thread': thread,
            'cursor': 0, 'watermark': 0, 'gap': False, 'page_seen': False,
            'retired': False, 'fingerprints': {}}
        return finish(state, out)
    except (Invalid, KeyError, TypeError, ValueError) as exc:
        return fault(state, str(exc) if isinstance(exc, Invalid) else 'ENROLLMENT_INVALID')


def _turn(state, thread, turn_id, stream):
    key = encoded([thread, identifier(turn_id)])
    if key in state['turns']:
        require(state['turns'][key]['stream'] == stream, 'TURN_STREAM_CHANGED')
    return state['turns'].setdefault(key, {'thread': thread, 'turn_id': turn_id, 'stream': stream,
        'operation_id': None, 'started': False, 'terminal': False, 'usage_seen': False})


def _apply_event(state, stream, event):
    kind, payload = event.get('native_type'), event['payload']
    if kind not in ('turn/started', 'turn/completed', 'thread/tokenUsage/updated'):
        return
    thread = state['threads'][stream['thread']]
    require(payload.get('thread_id') == thread['native_thread_id'], 'NATIVE_THREAD_MISMATCH')
    require(payload.get('threadId') == payload.get('thread_id'), 'THREAD_ALIAS_MISMATCH')
    turn_id = identifier(payload.get('turn_id'))
    turn = _turn(state, stream['thread'], turn_id, stream_id(stream['scope'], stream['epoch']))
    operation = event.get('operation_id')
    if kind == 'thread/tokenUsage/updated':
        require(event['category'] == 'tool_activity', 'USAGE_CATEGORY_INVALID')
        require(payload.get('turnId') == turn_id, 'TURN_ALIAS_MISMATCH')
        usage = payload.get('tokenUsage')
        require(type(usage) is dict, 'USAGE_SHAPE_INVALID')
        total = None
        for name in ('total', 'last'):
            counters = usage.get(name)
            require(type(counters) is dict and set(COUNTERS) <= set(counters), 'USAGE_SHAPE_INVALID')
            for field in COUNTERS:
                number(counters[field])
            number(counters.get('cacheWriteInputTokens', 0))
            if name == 'total':
                total = {field: counters[field] for field in COUNTERS}
                total['cacheWriteInputTokens'] = counters.get('cacheWriteInputTokens', 0)
        window = usage.get('modelContextWindow')
        require(window is None or type(window) is int and 0 <= window <= MAX_INT, 'USAGE_SHAPE_INVALID')
        require(total['totalTokens'] >= thread['high_water'], 'USAGE_COUNTER_RESET_OR_REGRESSION')
        previous = thread['components']
        require(previous is None or all(total[k] >= previous[k] for k in previous), 'USAGE_COMPONENT_REGRESSION')
        require(operation is None or turn['operation_id'] in (None, operation), 'USAGE_OPERATION_MISMATCH')
        if operation is not None:
            turn['operation_id'] = identifier(operation)
        thread['components'] = total
        thread['high_water'] = total['totalTokens']
        turn['usage_seen'] = True
        return
    require(event['category'] == 'turn_state', 'TURN_CATEGORY_INVALID')
    require(type(payload.get('turn')) is dict and payload['turn'].get('id') == turn_id, 'TURN_ALIAS_MISMATCH')
    identifier(operation)
    require(turn['operation_id'] in (None, operation), 'TURN_OPERATION_MISMATCH')
    turn['operation_id'] = operation
    if kind == 'turn/started':
        require(payload.get('delivery_phase') == 'started', 'START_NOT_CANONICAL')
        require(not turn['terminal'], 'TURN_STARTED_AFTER_TERMINAL')
        require(not any(other is not turn and other['started'] and not other['terminal']
                        for other in state['turns'].values()), 'CONCURRENT_NATIVE_TURNS')
        turn['started'] = True
    else:
        outcomes = {'completed': 'success', 'failed': 'failed', 'interrupted': 'interrupted'}
        expected = outcomes.get(payload['turn'].get('status'))
        require(expected is not None and payload.get('delivery_phase') == 'terminal'
                and payload.get('delivery_outcome') == expected, 'TERMINAL_NOT_CANONICAL')
        turn['terminal'] = True


def _coverage_reasons(state):
    reasons = list(state['faults'])
    if not state['streams']:
        reasons.append('NO_ENROLLED_EVENT_STREAM')
    if any(r['stream'] is None for r in state['requests'].values()):
        reasons.append('RESERVED_STREAM_NOT_BOUND')
    for stream in state['streams'].values():
        if not stream['page_seen']:
            reasons.append('STREAM_NOT_OBSERVED')
        if stream['gap']:
            reasons.append('GAP_PENDING')
        if stream['cursor'] < stream['watermark']:
            reasons.append('REPLAY_BACKLOG')
    operations = {(r['stream'], r['operation_id']) for r in state['requests'].values() if r['operation_id'] is not None}
    for turn in state['turns'].values():
        if not turn['started']:
            reasons.append('TURN_START_MISSING')
        if not turn['terminal']:
            reasons.append('TURN_TERMINAL_MISSING')
        if turn['terminal'] and not turn['usage_seen']:
            reasons.append('TERMINAL_USAGE_MISSING')
        if (turn['stream'], turn['operation_id']) not in operations:
            reasons.append('OPERATION_NOT_BOUND_TO_REQUEST')
    return sorted(set(reasons))


def _settle(state):
    request_id = state['current_request']
    if request_id is None or _coverage_reasons(state):
        return
    request = state['requests'][request_id]
    matching = [t for t in state['turns'].values()
                if t['stream'] == request['stream'] and t['operation_id'] == request['operation_id']]
    if request['operation_id'] is not None and len(matching) == 1:
        request['state'] = 'settled_observed'
        state['current_request'] = None


def observe(state, *, stream, after_sequence, page):
    """Consume read_execution_events data, not an HTTP envelope or native frame.

    Identical already-seen events are replay, not new usage. An old snapshot
    cannot lower a watermark or clear a gap. Invalid pages commit no partial
    accounting, and latch a typed fault that blocks further admissions.
    """
    try:
        require(stream in state['streams'], 'STREAM_NOT_ENROLLED')
        prior = state['streams'][stream]
        number(after_sequence, MAX_SEQUENCE)
        require(after_sequence <= prior['cursor'], 'CURSOR_SKIP')
        require(type(page) is dict and page.get('scope') == prior['scope'], 'PAGE_SCOPE_MISMATCH')
        require(page.get('stream_epoch') == prior['epoch'], 'PAGE_EPOCH_MISMATCH')
        events = page.get('events')
        require(type(events) is list and len(events) <= 1000, 'PAGE_EVENTS_INVALID')
        require(number(page.get('count'), 1000) == len(events), 'PAGE_COUNT_MISMATCH')
        next_cursor = number(page.get('next_after_sequence'), MAX_SEQUENCE)
        watermark = number(page.get('committed_contiguous'), MAX_SEQUENCE)
        require(next_cursor == after_sequence + len(events) and next_cursor <= watermark, 'PAGE_CURSOR_INVALID')
        require(type(page.get('gap_pending')) is bool and type(page.get('has_more')) is bool, 'PAGE_FLAGS_INVALID')
        require(page['has_more'] == (next_cursor < watermark), 'PAGE_BACKLOG_INVALID')
        out = deepcopy(state)
        target = out['streams'][stream]
        for index, event in enumerate(events, after_sequence + 1):
            require(type(event) is dict and type(event.get('payload')) is dict, 'EVENT_SHAPE_INVALID')
            require(type(event.get('sequence')) is int and event['sequence'] == index, 'EVENT_CURSOR_INVALID')
            require(all(event.get(k) == prior['scope'][k] for k in ('server_id', 'executor_id', 'session_id'))
                    and event.get('stream_epoch') == prior['epoch'], 'EVENT_SCOPE_MISMATCH')
            require(type(event.get('category')) is str, 'EVENT_SHAPE_INVALID')
            require(event.get('native_type') is None or type(event.get('native_type')) is str, 'EVENT_SHAPE_INVALID')
            marker = fingerprint({k: v for k, v in event.items() if k != 'received_at'})
            key = str(index)
            if index <= target['cursor']:
                require(target['fingerprints'].get(key) == marker, 'REPLAY_CONFLICT')
                continue
            require(not target['retired'], 'RETIRED_STREAM_ADVANCED')
            require(index == target['cursor'] + 1, 'EVENT_CURSOR_SKIP')
            require(len(target['fingerprints']) < 100000, 'COLLECTOR_CAPACITY_REACHED')
            _apply_event(out, target, event)
            target['fingerprints'][key] = marker
            target['cursor'] = index
        if watermark > prior['watermark']:
            target['gap'] = page['gap_pending']
        elif page['gap_pending']:
            target['gap'] = True
        target['watermark'] = max(watermark, prior['watermark'])
        target['page_seen'] = True
        _settle(out)
        return finish(state, out)
    except (Invalid, KeyError, TypeError, ValueError, OverflowError) as exc:
        return fault(state, str(exc) if isinstance(exc, Invalid) else 'PAGE_INVALID')


def summary(state):
    total = sum(t['high_water'] - t['baseline'] for t in state['threads'].values())
    reasons = _coverage_reasons(state)
    if state['current_request'] is not None:
        reasons.append('SERIAL_REQUEST_UNSETTLED')
    if total >= state['stop_at']:
        reasons.append('PREVENTIVE_THRESHOLD_REACHED')
    if len(state['requests']) >= state['max_requests']:
        reasons.append('MAX_PRODUCTIVE_ADMISSIONS_REACHED')
    return {'known_observed_tokens': total, 'observed_prefix_covered': not _coverage_reasons(state),
            'can_reserve_new_request': not reasons, 'reasons': sorted(set(reasons)),
            'request_preventive_interrupt': total >= state['stop_at'] and state['current_request'] is not None,
            'at_or_above_operational_tolerance': total >= state['tolerance'],
            'stop_at': state['stop_at'], 'operational_tolerance': state['tolerance'],
            'reserved_requests': len(state['requests']), 'max_productive_admissions': state['max_requests'],
            'current_request': state['current_request'], 'revision': state['revision'],
            'final_usage_authoritative': False,
            'limitation': 'usage_seen means any usage observation for a turn, not a guaranteed final update. Observed totals and interrupts are asynchronous, not an atomic hard cap.'}


def reserve(state, *, request_id, stream, stage):
    """Return (state, dispatch_permitted). Persist state before dispatch.

    Repeating a request never grants a second dispatch. Persistence/CAS and
    exactly-once HTTP recovery belong to the controller, not this pure module.
    """
    try:
        identifier(request_id)
        require(stage in ('setup_test', 'useful_work', 'continuation'), 'STAGE_INVALID')
        require(stream in state['streams'], 'STREAM_NOT_ENROLLED')
        if request_id in state['requests']:
            old = state['requests'][request_id]
            require(old['stream'] == stream and old['stage'] == stage, 'REQUEST_ID_REBOUND')
            return deepcopy(state), False
        if not summary(state)['can_reserve_new_request']:
            return deepcopy(state), False
        out = deepcopy(state)
        out['requests'][request_id] = {'stream': stream, 'stage': stage,
                                      'operation_id': None, 'state': 'reserved'}
        out['current_request'] = request_id
        return finish(state, out), True
    except (Invalid, KeyError, TypeError, ValueError) as exc:
        return fault(state, str(exc) if isinstance(exc, Invalid) else 'RESERVATION_INVALID'), False


def prearm(state, *, request_id, scope, stage):
    """Reserve before runtime.start creates session/epoch/native-thread IDs.

    scope is the six-field canonical binding already known by TerminalWork.
    The controller persists this exclusive reservation BEFORE setup:test or
    runtime.start, then resolves the same durable intent and calls bind_stream.
    No further admission is possible until binding and replay from zero settle.
    This does not itself prove native freshness or resolve the durable intent.
    """
    try:
        identifier(request_id)
        require(stage in ('setup_test', 'useful_work', 'continuation'), 'STAGE_INVALID')
        require(type(scope) is dict and set(scope) == set(PRE_SCOPE), 'PRE_SCOPE_INVALID')
        for value in scope.values():
            identifier(value)
        if request_id in state['requests']:
            old = state['requests'][request_id]
            require(old.get('pre_scope') == scope and old['stage'] == stage, 'REQUEST_ID_REBOUND')
            return deepcopy(state), False
        reasons = summary(state)['reasons']
        if any(reason != 'NO_ENROLLED_EVENT_STREAM' for reason in reasons):
            return deepcopy(state), False
        out = deepcopy(state)
        out['requests'][request_id] = {'stream': None, 'pre_scope': deepcopy(scope),
            'stage': stage, 'operation_id': None, 'state': 'reserved'}
        out['current_request'] = request_id
        return finish(state, out), True
    except (Invalid, KeyError, TypeError, ValueError) as exc:
        return fault(state, str(exc) if isinstance(exc, Invalid) else 'RESERVATION_INVALID'), False


def bind_stream(state, *, request_id, scope, epoch, native_thread_id, baseline_total, baseline_basis):
    """Bind the SAME resolved request, then replay its canonical page from zero.

    A new stream must not already be enrolled or share an existing native thread;
    already-known streams use reserve, and explicit settled handover uses enroll.
    A response-loss controller may recover and call this without resubmitting.
    """
    try:
        require(request_id in state['requests'], 'REQUEST_NOT_RESERVED')
        request = state['requests'][request_id]
        require(request.get('pre_scope') == {k: scope[k] for k in PRE_SCOPE}, 'PRE_SCOPE_MISMATCH')
        key = stream_id(scope, epoch)
        if request['stream'] is not None:
            require(request['stream'] == key, 'REQUEST_STREAM_REBOUND')
            # Reuse enrollment validation for exact scope, thread and baseline.
            return enroll(state, scope=scope, epoch=epoch, native_thread_id=native_thread_id,
                          baseline_total=baseline_total, baseline_basis=baseline_basis)
        require(state['current_request'] == request_id, 'REQUEST_NOT_CURRENT')
        require(key not in state['streams'], 'PREARM_STREAM_ALREADY_ENROLLED')
        thread = encoded([scope['server_id'], scope['executor_id'], native_thread_id])
        require(thread not in state['threads'], 'PREARM_THREAD_ALREADY_ENROLLED')
        out = enroll(state, scope=scope, epoch=epoch, native_thread_id=native_thread_id,
                     baseline_total=baseline_total, baseline_basis=baseline_basis)
        if out['faults'] != state['faults']:
            return out
        out['requests'][request_id]['stream'] = key
        return finish(state, out)
    except (Invalid, KeyError, TypeError, ValueError) as exc:
        return fault(state, str(exc) if isinstance(exc, Invalid) else 'STREAM_BINDING_INVALID')


def bind_operation(state, *, request_id, operation_id):
    """Bind only after the controller resolves the same canonical durable intent."""
    try:
        identifier(operation_id)
        require(request_id in state['requests'], 'REQUEST_NOT_RESERVED')
        out = deepcopy(state)
        request = out['requests'][request_id]
        require(request['stream'] is not None, 'RESERVED_STREAM_NOT_BOUND')
        require(request['operation_id'] in (None, operation_id), 'OPERATION_REBOUND')
        require(not any(k != request_id and r['stream'] == request['stream'] and r['operation_id'] == operation_id
                        for k, r in out['requests'].items()), 'OPERATION_REUSED')
        request['operation_id'] = operation_id
        _settle(out)
        return finish(state, out)
    except (Invalid, KeyError, TypeError, ValueError) as exc:
        return fault(state, str(exc) if isinstance(exc, Invalid) else 'BINDING_INVALID')


def response_lost(state, *, request_id):
    """Pure bookkeeping; never retries, creates an ID, or clears the reservation."""
    if request_id not in state['requests']:
        return fault(state, 'REQUEST_NOT_RESERVED')
    out = deepcopy(state)
    if out['requests'][request_id]['state'] != 'settled_observed':
        out['requests'][request_id]['state'] = 'response_unknown'
    return finish(state, out)


def checkpoint(state):
    body = deepcopy(state)
    return {'format': 'm1-token-collector-v1', 'state': body, 'sha256': fingerprint(body)}


def restore(document):
    """Detect incomplete/accidentally changed storage, not hostile tampering.

    No fallback to a zero state on failure. A fresh campaign must be explicit.
    """
    require(type(document) is dict and document.get('format') == 'm1-token-collector-v1', 'CHECKPOINT_INVALID')
    state = document.get('state')
    require(type(state) is dict and state.get('version') == 1 and state.get('stop_at') == 100000
            and state.get('tolerance') == 700000 and state.get('max_requests') == 6
            and document.get('sha256') == fingerprint(state), 'CHECKPOINT_INVALID')
    require(set(state) == set(initial_state()), 'CHECKPOINT_INVALID')
    return deepcopy(state)
