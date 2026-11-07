"""Synthetic deterministic tests. Core translation is pure; no native runtime."""
from copy import deepcopy
from dataclasses import asdict, replace
import json

import pytest
from nexus_connector_core.native.adapter_types import HarnessEvent
from nexus_connector_core.native.event_ingest import translate_native_event

import token_collector as c


def scope(suffix='a'):
    return {'server_id': 'server', 'executor_id': 'executor', 'binding_id': 'binding-' + suffix,
            'agent_id': 'agent-' + suffix, 'workspace_id': 'workspace', 'workspace_binding_id': 'wb-' + suffix,
            'session_id': 'session-' + suffix, **{name: 1 for name in c.REVISIONS}}


def counters(total):
    return {'totalTokens': total, 'inputTokens': total, 'cachedInputTokens': total // 2,
            'outputTokens': 0, 'reasoningOutputTokens': 0}


def event(sequence, method, *, total=20, op='operation', turn='turn', thread='thread', selected=None, epoch='epoch', status='completed'):
    selected = selected or scope()
    payload = {'threadId': thread}
    kind, phase, outcome, operation_id = 'tool_activity', None, None, None
    if method == 'thread/tokenUsage/updated':
        payload.update(turnId=turn, tokenUsage={'total': counters(total), 'last': counters(total // 3), 'modelContextWindow': 258400})
    elif method in ('turn/started', 'turn/completed'):
        payload['turn'] = {'id': turn, 'status': 'inProgress' if method == 'turn/started' else status}
        kind = 'turn_started' if method == 'turn/started' else 'turn_completed'
        phase = 'started' if method == 'turn/started' else 'terminal'
        outcome = None if phase == 'started' else {'completed': 'success', 'interrupted': 'interrupted', 'failed': 'failed'}[status]
        operation_id = op
    native = HarnessEvent(session_id='native-session', harness_kind='codex', kind=kind,
        native_event=method, occurred_at='2026-11-07T00:00:00Z', payload=payload,
        thread_id=thread, turn_id=turn, operation_id=operation_id, delivery_phase=phase, delivery_outcome=outcome)
    translated = translate_native_event(native, server_id=selected['server_id'], executor_id=selected['executor_id'],
        session_id=selected['session_id'], stream_epoch=epoch, native_session_id='native-session')
    return asdict(replace(translated, sequence=sequence)) | {'received_at': '2026-11-07T00:00:01Z'}


def page(events=(), *, selected=None, epoch='epoch', after=0, committed=None, gap=False):
    next_cursor = after + len(events)
    watermark = next_cursor if committed is None else committed
    return {'scope': selected or scope(), 'stream_epoch': epoch, 'events': list(events), 'count': len(events),
            'next_after_sequence': next_cursor, 'committed_contiguous': watermark,
            'gap_pending': gap, 'has_more': next_cursor < watermark}


def enroll_ready(state=None, *, selected=None, epoch='epoch', thread='thread', baseline=0):
    selected = selected or scope()
    state = c.enroll(state or c.initial_state(), scope=selected, epoch=epoch, native_thread_id=thread,
        baseline_total=baseline, baseline_basis='confirmed_fresh_thread' if baseline == 0 else 'retained_pre_campaign_usage')
    key = c.stream_id(selected, epoch)
    state = c.observe(state, stream=key, after_sequence=0, page=page(selected=selected, epoch=epoch))
    return state, key


def begin(state, key, request='request', op='operation', stage='useful_work'):
    state, allowed = c.reserve(state, request_id=request, stream=key, stage=stage)
    assert allowed
    return c.bind_operation(state, request_id=request, operation_id=op)


def complete(state, key, *, total=20, op='operation', turn='turn', thread='thread', selected=None, epoch='epoch'):
    after = state['streams'][key]['cursor']
    items = [event(after + 1, 'turn/started', op=op, turn=turn, thread=thread, selected=selected, epoch=epoch),
             event(after + 2, 'thread/tokenUsage/updated', total=total, turn=turn, thread=thread, selected=selected, epoch=epoch),
             event(after + 3, 'turn/completed', op=op, turn=turn, thread=thread, selected=selected, epoch=epoch)]
    payload = page(items, after=after, selected=selected, epoch=epoch)
    return c.observe(state, stream=key, after_sequence=after, page=payload), payload


def test_core_translation_and_replay_count_only_cumulative_total():
    state, key = enroll_ready()
    state = begin(state, key)
    prior = deepcopy(state)
    completed, payload = complete(state, key, total=8147)
    assert state == prior  # Reducers do not mutate caller state.
    sample = payload['events'][1]
    assert sample['native_type'] == 'thread/tokenUsage/updated' and sample['operation_id'] is None
    assert sample['payload']['threadId'] == sample['payload']['thread_id'] == 'thread'
    assert sample['payload']['turnId'] == sample['payload']['turn_id'] == 'turn'
    assert c.summary(completed)['known_observed_tokens'] == 8147
    assert c.summary(completed)['can_reserve_new_request']
    replay = deepcopy(payload)
    for item in replay['events']:
        item['received_at'] = 'another transport presentation timestamp'
    assert c.observe(completed, stream=key, after_sequence=0, page=replay) == completed
    assert c.summary(completed)['final_usage_authoritative'] is False


def test_overlapping_pages_after_response_loss_never_double_charge():
    state, key = enroll_ready()
    state = begin(state, key)
    _, all_events = complete(state, key, total=80)
    events = all_events['events']
    state = c.observe(state, stream=key, after_sequence=0, page=page(events[:2], committed=3))
    assert c.summary(state)['known_observed_tokens'] == 80
    assert 'REPLAY_BACKLOG' in c.summary(state)['reasons']
    state = c.observe(state, stream=key, after_sequence=1, page=page(events[1:], after=1))
    assert c.summary(state)['known_observed_tokens'] == 80 and c.summary(state)['can_reserve_new_request']


def test_reservation_survives_json_checkpoint_and_unknown_response_until_canonical_binding():
    state, key = enroll_ready()
    state, allowed = c.reserve(state, request_id='request', stream=key, stage='setup_test')
    assert allowed
    state = c.restore(json.loads(json.dumps(c.checkpoint(c.response_lost(state, request_id='request')))))
    _, duplicate = c.reserve(state, request_id='request', stream=key, stage='setup_test')
    _, second = c.reserve(state, request_id='different', stream=key, stage='useful_work')
    assert not duplicate and not second
    state, _ = complete(state, key)
    assert state['current_request'] == 'request'
    assert 'OPERATION_NOT_BOUND_TO_REQUEST' in c.summary(state)['reasons']
    state = c.bind_operation(state, request_id='request', operation_id='operation')
    assert state['current_request'] is None
    assert c.summary(state)['known_observed_tokens'] == 20


def test_missing_or_modified_checkpoint_never_falls_back_to_zero():
    state, _ = enroll_ready()
    document = c.checkpoint(state)
    document['state']['threads'][next(iter(document['state']['threads']))]['high_water'] = 123
    with pytest.raises(c.Invalid, match='CHECKPOINT_INVALID'):
        c.restore(document)
    with pytest.raises(c.Invalid, match='CHECKPOINT_INVALID'):
        c.restore({})


@pytest.mark.parametrize('change,reason', [
    (lambda p: p.update(stream_epoch='other'), 'PAGE_EPOCH_MISMATCH'),
    (lambda p: p['scope'].update(session_owner_generation=2), 'PAGE_SCOPE_MISMATCH'),
    (lambda p: p.update(count=True), 'COUNTER_INVALID'),
    (lambda p: p.update(next_after_sequence=9), 'PAGE_CURSOR_INVALID'),
    (lambda p: p.update(has_more=True), 'PAGE_BACKLOG_INVALID'),
    (lambda p: p['events'][0].update(sequence=True), 'EVENT_CURSOR_INVALID'),
])
def test_invalid_page_is_atomic_and_latches_admission_stop(change, reason):
    state, key = enroll_ready()
    state = begin(state, key)
    _, data = complete(state, key)
    data = deepcopy(data)
    change(data)
    out = c.observe(state, stream=key, after_sequence=0, page=data)
    assert reason in out['faults']
    assert c.summary(out)['known_observed_tokens'] == 0 and out['streams'][key]['cursor'] == 0
    assert not c.summary(out)['can_reserve_new_request']


def test_scope_and_cursor_skip_are_not_silently_rebased():
    state, key = enroll_ready()
    skipped = c.observe(state, stream=key, after_sequence=1, page=page(after=1))
    assert skipped['faults'] == ['CURSOR_SKIP']
    wrong = event(1, 'unrelated', selected=scope('b'))
    out = c.observe(state, stream=key, after_sequence=0, page=page([wrong]))
    assert out['faults'] == ['EVENT_SCOPE_MISMATCH']


def test_gap_blocks_until_contiguous_progress_and_old_snapshot_cannot_clear_it():
    state, key = enroll_ready()
    state = c.observe(state, stream=key, after_sequence=0, page=page(gap=True))
    old = c.observe(state, stream=key, after_sequence=0, page=page())
    assert old['streams'][key]['gap'] and 'GAP_PENDING' in c.summary(old)['reasons']
    state = c.observe(old, stream=key, after_sequence=0, page=page([event(1, 'thread/status/changed')]))
    assert not state['streams'][key]['gap'] and c.summary(state)['can_reserve_new_request']


def test_terminal_missing_and_terminal_without_usage_both_stop_new_work():
    state, key = enroll_ready()
    state = begin(state, key)
    start = event(1, 'turn/started')
    state = c.observe(state, stream=key, after_sequence=0, page=page([start]))
    assert 'TURN_TERMINAL_MISSING' in c.summary(state)['reasons']
    terminal = event(2, 'turn/completed')
    state = c.observe(state, stream=key, after_sequence=1, page=page([terminal], after=1))
    assert 'TERMINAL_USAGE_MISSING' in c.summary(state)['reasons']
    assert state['current_request'] == 'request'
    # A late observation is counted, without pretending the schema promises it is final.
    state = c.observe(state, stream=key, after_sequence=2,
        page=page([event(3, 'thread/tokenUsage/updated', total=30)], after=2))
    assert state['current_request'] is None and c.summary(state)['known_observed_tokens'] == 30
    assert c.summary(state)['final_usage_authoritative'] is False


@pytest.mark.parametrize('bad', [-1, True, 1.5, '20', 2**63])
def test_malformed_usage_is_unknown_and_does_not_consume_zero(bad):
    state, key = enroll_ready()
    state = begin(state, key)
    _, data = complete(state, key)
    data['events'][1]['payload']['tokenUsage']['total']['totalTokens'] = bad
    out = c.observe(state, stream=key, after_sequence=0, page=data)
    assert 'COUNTER_INVALID' in out['faults'] and not c.summary(out)['observed_prefix_covered']


def test_counter_reset_retains_known_minimum_and_never_resets_campaign():
    state, key = enroll_ready()
    state, _ = complete(begin(state, key), key, total=50)
    state = begin(state, key, request='second', op='op2')
    out, _ = complete(state, key, total=10, op='op2', turn='turn2')
    assert out['faults'] == ['USAGE_COUNTER_RESET_OR_REGRESSION']
    assert c.summary(out)['known_observed_tokens'] == 50
    assert not c.summary(out)['can_reserve_new_request']


def test_conflicting_replay_cannot_change_usage_or_erase_known_total():
    state, key = enroll_ready()
    state, data = complete(begin(state, key), key, total=40)
    data['events'][1]['payload']['tokenUsage']['total'] = counters(70)
    out = c.observe(state, stream=key, after_sequence=0, page=data)
    assert out['faults'] == ['REPLAY_CONFLICT'] and c.summary(out)['known_observed_tokens'] == 40


def test_explicit_same_thread_epoch_handover_counts_only_high_water_delta():
    state, key = enroll_ready()
    state, original_page = complete(begin(state, key), key, total=40)
    state, new_key = enroll_ready(state, epoch='epoch-2')
    state = begin(state, new_key, request='second', op='op2')
    state, _ = complete(state, new_key, total=70, op='op2', turn='turn2', epoch='epoch-2')
    assert c.summary(state)['known_observed_tokens'] == 70
    out = c.observe(state, stream=key, after_sequence=0, page=original_page)
    assert out == state
    advanced = c.observe(state, stream=key, after_sequence=3,
                         page=page([event(4, 'thread/status/changed')], after=3))
    assert advanced['faults'] == ['RETIRED_STREAM_ADVANCED']


def test_no_baseline_or_changing_baseline_cannot_admit_or_rebase():
    out = c.enroll(c.initial_state(), scope=scope(), epoch='epoch', native_thread_id='thread',
                   baseline_total=None, baseline_basis='confirmed_fresh_thread')
    assert not c.summary(out)['can_reserve_new_request']
    state, key = enroll_ready(baseline=100)
    state, _ = complete(begin(state, key), key, total=130)
    assert c.summary(state)['known_observed_tokens'] == 30
    out = c.enroll(state, scope=scope(), epoch='epoch-2', native_thread_id='thread',
                   baseline_total=0, baseline_basis='confirmed_fresh_thread')
    assert out['faults'] == ['BASELINE_CHANGED']


@pytest.mark.parametrize('total,allowed', [(99999, True), (100000, False), (700000, False)])
def test_operational_stop_is_100k_not_the_700k_tolerance(total, allowed):
    state, key = enroll_ready()
    state, _ = complete(begin(state, key), key, total=total)
    _, dispatch = c.reserve(state, request_id='next', stream=key, stage='continuation')
    assert dispatch is allowed
    assert c.summary(state)['operational_tolerance'] == 700000


def test_reaching_threshold_during_turn_requests_preventive_interrupt():
    state, key = enroll_ready()
    state = begin(state, key)
    data = page([event(1, 'turn/started'), event(2, 'thread/tokenUsage/updated', total=100000)])
    state = c.observe(state, stream=key, after_sequence=0, page=data)
    assert c.summary(state)['request_preventive_interrupt']
    assert not c.summary(state)['can_reserve_new_request']


def test_six_total_reservations_include_setup_and_seventh_is_refused():
    state, key = enroll_ready()
    for index in range(6):
        request, op, turn = f'req{index}', f'op{index}', f'turn{index}'
        state = begin(state, key, request, op, 'setup_test' if index < 2 else 'useful_work')
        state, _ = complete(state, key, total=(index + 1) * 10, op=op, turn=turn)
    out, allowed = c.reserve(state, request_id='seventh', stream=key, stage='continuation')
    assert not allowed and out == state
    assert c.summary(state)['reserved_requests'] == 6
    assert 'MAX_PRODUCTIVE_ADMISSIONS_REACHED' in c.summary(state)['reasons']
    _, duplicate = c.reserve(state, request_id='req0', stream=key, stage='setup_test')
    assert not duplicate


def test_operation_id_collision_in_another_stream_does_not_settle_reserved_request():
    state, a = enroll_ready()
    state, b = enroll_ready(state, selected=scope('b'), thread='thread-b')
    state = begin(state, a, request='for-a', op='collision')
    state, _ = complete(state, b, total=30, op='collision', thread='thread-b', selected=scope('b'))
    assert state['current_request'] == 'for-a'
    assert 'OPERATION_NOT_BOUND_TO_REQUEST' in c.summary(state)['reasons']
    assert not c.summary(state)['can_reserve_new_request']


def test_concurrent_native_turn_is_unconfirmed_even_on_separate_threads():
    state, a = enroll_ready()
    state, b = enroll_ready(state, selected=scope('b'), thread='thread-b')
    state = begin(state, a)
    state = c.observe(state, stream=a, after_sequence=0, page=page([event(1, 'turn/started')]))
    data = page([event(1, 'turn/started', op='other', thread='thread-b', selected=scope('b'))], selected=scope('b'))
    state = c.observe(state, stream=b, after_sequence=0, page=data)
    assert state['faults'] == ['CONCURRENT_NATIVE_TURNS']


def test_prearm_before_first_setup_persists_and_reconciles_without_second_dispatch():
    selected = scope()
    pre_scope = {k: selected[k] for k in c.PRE_SCOPE}
    state, allowed = c.prearm(c.initial_state(), request_id='setup', scope=pre_scope, stage='setup_test')
    assert allowed and state['streams'] == {} and len(state['requests']) == 1
    state = c.restore(json.loads(json.dumps(c.checkpoint(c.response_lost(state, request_id='setup')))))
    assert c.summary(state)['current_request'] == 'setup'
    _, duplicate = c.prearm(state, request_id='setup', scope=pre_scope, stage='setup_test')
    _, another = c.prearm(state, request_id='new', scope=pre_scope, stage='setup_test')
    assert not duplicate and not another
    state = c.bind_stream(state, request_id='setup', scope=selected, epoch='epoch',
                          native_thread_id='thread', baseline_total=0, baseline_basis='confirmed_fresh_thread')
    key = c.stream_id(selected, 'epoch')
    assert 'STREAM_NOT_OBSERVED' in c.summary(state)['reasons']
    state = c.bind_operation(state, request_id='setup', operation_id='operation')
    state, _ = complete(state, key, total=400)
    assert c.summary(state)['known_observed_tokens'] == 400
    assert c.summary(state)['can_reserve_new_request'] and len(state['requests']) == 1
    assert c.bind_stream(state, request_id='setup', scope=selected, epoch='epoch',
        native_thread_id='thread', baseline_total=0, baseline_basis='confirmed_fresh_thread') == state


@pytest.mark.parametrize('field', c.PRE_SCOPE)
def test_prearmed_request_cannot_bind_another_canonical_scope(field):
    selected = scope()
    state, allowed = c.prearm(c.initial_state(), request_id='setup',
        scope={k: selected[k] for k in c.PRE_SCOPE}, stage='setup_test')
    assert allowed
    selected[field] = 'wrong'
    state = c.bind_stream(state, request_id='setup', scope=selected, epoch='epoch',
        native_thread_id='thread', baseline_total=0, baseline_basis='confirmed_fresh_thread')
    assert state['faults'] == ['PRE_SCOPE_MISMATCH']
    assert state['streams'] == {} and state['requests']['setup']['stream'] is None


def test_six_prearmed_setup_reservations_also_exhaust_the_shared_budget():
    state = c.initial_state()
    for index in range(6):
        selected, thread, request = scope(str(index)), f'thread{index}', f'request{index}'
        state, allowed = c.prearm(state, request_id=request,
            scope={k: selected[k] for k in c.PRE_SCOPE}, stage='setup_test')
        assert allowed
        state = c.bind_stream(state, request_id=request, scope=selected, epoch='epoch',
            native_thread_id=thread, baseline_total=0, baseline_basis='confirmed_fresh_thread')
        state = c.bind_operation(state, request_id=request, operation_id='operation')
        state, _ = complete(state, c.stream_id(selected, 'epoch'), selected=selected, thread=thread)
    out, allowed = c.prearm(state, request_id='seventh',
        scope={k: scope()[k] for k in c.PRE_SCOPE}, stage='useful_work')
    assert not allowed and out == state
    assert c.summary(state)['known_observed_tokens'] == 120


def test_usage_operation_before_start_cannot_be_rebound_to_another_request():
    state, key = enroll_ready()
    state = begin(state, key)
    usage = event(1, 'thread/tokenUsage/updated')
    usage['operation_id'] = 'other-operation'
    state = c.observe(state, stream=key, after_sequence=0, page=page([usage]))
    assert next(iter(state['turns'].values()))['operation_id'] == 'other-operation'
    state = c.observe(state, stream=key, after_sequence=1,
        page=page([event(2, 'turn/started')], after=1))
    assert state['faults'] == ['TURN_OPERATION_MISMATCH']
    assert state['current_request'] == 'request'


def test_delayed_usage_after_settlement_still_raises_campaign_high_water():
    state, key = enroll_ready()
    state, _ = complete(begin(state, key), key, total=40)
    assert c.summary(state)['can_reserve_new_request']
    state = c.observe(state, stream=key, after_sequence=3,
        page=page([event(4, 'thread/tokenUsage/updated', total=100000)], after=3))
    assert c.summary(state)['known_observed_tokens'] == 100000
    assert not c.summary(state)['can_reserve_new_request']


def test_retired_stream_cannot_reserve_after_explicit_epoch_handover():
    state, old_key = enroll_ready()
    state, _ = complete(begin(state, old_key), old_key)
    state, new_key = enroll_ready(state, epoch='epoch-2')
    assert state['streams'][old_key]['retired'] and not state['streams'][new_key]['retired']
    assert c.summary(state)['can_reserve_new_request']
    out, dispatch = c.reserve(state, request_id='new-request', stream=old_key, stage='useful_work')
    assert not dispatch and out == state
    assert 'new-request' not in out['requests'] and out['current_request'] is None
    _, active_dispatch = c.reserve(state, request_id='new-request', stream=new_key, stage='useful_work')
    assert active_dispatch
