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


