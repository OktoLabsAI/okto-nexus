"""Durable coordination checkpoints and passive waits under controlled faults.

The MCP adapter's separate TCP suite exercises transport and real canonical
transactions. These tests control clocks, persistence and every facade boundary.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus.application.terminal_coordination import TerminalCoordination


OPS = ('message_create', 'handoff_create')
SCOPE = dict(origin='https://nexus.example', server_id='server', agent_id='caller', workspace_id='workspace')
CONTENT = 'PRIVATE-CONTENT-NOT-A-CHECKPOINT'
SECRET = 'PRIVATE-SESSION-SECRET-NOT-A-CHECKPOINT'


class Clock:
    def __init__(self):
        self.local = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
        self.server = self.local + timedelta(hours=2)
        self.elapsed = 0

    def sleep(self, seconds):
        self.elapsed += seconds
        self.local += timedelta(seconds=seconds)
        self.server += timedelta(seconds=seconds)


class Checkpoint:
    def __init__(self):
        self.saved = []
        self.fail_state = None

    def save(self, document):
        if self.fail_state == document['state']:
            self.fail_state = None
            raise OSError('Injected checkpoint persistence failure')
        self.saved.append(deepcopy(document))

    @property
    def last(self):
        return deepcopy(self.saved[-1]) if self.saved else None


class MCP:
    def __init__(self, clock, checkpoint):
        self.clock, self.checkpoint = clock, checkpoint
        self.calls, self.receipts, self.effects = [], {}, []
        self.discovery_change = None
        self.creation_fault = None
        self.creation_state = 'created'
        self.receipt_change = None
        self.lookup_transition = None
        self.handoffs = [dict(handoff_id='handoff-1', workspace_id=SCOPE['workspace_id'], status='OPEN')]
        self.cursor = 7
        self.following_cursor = 7
        self.wait_failure = None

    def discover(self):
        self.calls.append(('discover', {}, None))
        contract = dict(revision=1, retention_days=30, operations=list(OPS),
            recovery_tool='coordination_request_get', response='references', observed_at=self.clock.server.isoformat())
        schemas = {name: dict(properties={field: {} for field in fields}) for name, fields in {
            'message_create': ('client_request_id', 'workspace_id', 'from_agent_id'),
            'handoff_create': ('client_request_id', 'workspace_id', 'from_agent_id'),
            'coordination_request_get': ('workspace_id', 'operation', 'client_request_id'),
            'handoff_get': ('passive', 'workspace_id', 'agent_id'),
            'event_cursor': ('passive', 'workspace_id', 'agent_id'),
            'event_wait': ('passive', 'workspace_id', 'agent_id'),
        }.items()}
        discovery = dict(info=dict(coordination_requests=contract,
            coordination_observation=dict(revision=1, passive=True, workspace_selector=True)), schemas=schemas)
        if self.discovery_change:
            self.discovery_change(discovery)
        return discovery

    def response(self, receipt):
        receipt = deepcopy(receipt)
        if self.clock.server >= datetime.fromisoformat(receipt['expires_at']):
            receipt['state'] = 'expired'
        if self.receipt_change:
            self.receipt_change(receipt)
        data = dict(status=receipt['state'], workspace_id=receipt['workspace_id'],
                    request_receipt=receipt, reused=False)
        if receipt['resource_id']:
            data['message_id' if receipt['operation'] == 'message_create' else 'handoff_id'] = receipt['resource_id']
        if receipt['approval_id']:
            data['approval_id'] = receipt['approval_id']
        return data

    def call(self, tool, arguments, *, timeout=None):
        self.calls.append((tool, deepcopy(arguments), timeout))
        if tool in OPS:
            # The ID and uncertainty marker must already be durable at the
            # exact boundary where productive transmission becomes possible.
            saved = self.checkpoint.last
            assert saved['state'] == 'uncertain'
            assert saved['client_request_id'] == arguments['client_request_id']
            fault, self.creation_fault = self.creation_fault, None
            if fault == 'before':
                raise ConnectionError('OUTCOME_UNKNOWN', 'Injected request loss', possible_effect=True)
            key = tool, arguments['client_request_id']
            if key not in self.receipts:
                self.effects.append(key)
                self.receipts[key] = dict(server_id=SCOPE['server_id'], actor_agent_id=SCOPE['agent_id'],
                    workspace_id=SCOPE['workspace_id'], operation=tool, client_request_id=key[1],
                    state=self.creation_state,
                    resource_id=('message-1' if tool == 'message_create' else 'handoff-1')
                        if self.creation_state == 'created' else None,
                    approval_id='approval-1' if self.creation_state == 'pending_approval' else None,
                    created_at=self.clock.server.isoformat(),
                    expires_at=(self.clock.server + timedelta(days=30)).isoformat())
            if fault == 'after':
                raise ConnectionError('OUTCOME_UNKNOWN', 'Injected response loss', possible_effect=True)
            return self.response(self.receipts[key])
        if tool == 'coordination_request_get':
            key = arguments['operation'], arguments['client_request_id']
            if key not in self.receipts:
                raise ConnectionError('NOT_FOUND', 'No retained receipt')
            if self.lookup_transition:
                self.receipts[key]['state'] = self.lookup_transition
                if self.lookup_transition == 'created':
                    self.receipts[key]['resource_id'] = 'handoff-1'
                self.lookup_transition = None
            return self.response(self.receipts[key])
        if tool == 'event_cursor':
            return dict(cursor=self.cursor)
        if tool == 'handoff_get':
            value = deepcopy(self.handoffs[0])
            if len(self.handoffs) > 1:
                self.handoffs.pop(0)
            return value
        if tool == 'event_wait':
            if self.wait_failure:
                raise self.wait_failure
            self.clock.sleep(arguments['timeout_seconds'])
            # Deliberately no visible event: the canonical reread must still run.
            return dict(events=[], next_cursor=self.following_cursor, timed_out=True)
        raise AssertionError('Unexpected tool ' + tool)


@pytest.fixture
def state():
    clock, checkpoint = Clock(), Checkpoint()
    mcp = MCP(clock, checkpoint)

    def reopen(saved=None):
        return TerminalCoordination(mcp, SCOPE, checkpoint.save, saved,
            now=lambda: clock.local, monotonic=lambda: clock.elapsed, sleep=clock.sleep)

    return SimpleNamespace(clock=clock, checkpoint=checkpoint, mcp=mcp, reopen=reopen, flow=reopen())


def arguments(operation):
    return dict(target=dict(strategy='direct', agent_id='worker'), trace_id='trace-original') | (
        dict(subject='Question', body=CONTENT, from_session_id='session-original', session_secret=SECRET)
        if operation == 'message_create' else
        dict(visibility='eligible', payload=dict(objective=CONTENT), session_id='session-original', session_secret=SECRET))


def productive_calls(state):
    return [(tool, args) for tool, args, _ in state.mcp.calls if tool in OPS]


@pytest.mark.parametrize('operation', OPS)
def test_checkpoint_failure_before_transmission_sends_no_productive_call(state, operation):
    state.checkpoint.fail_state = 'uncertain'
    with pytest.raises(ConnectionError) as caught:
        state.flow.submit(operation, 'durable:request', arguments(operation))
    assert caught.value.code == 'CHECKPOINT_WRITE_FAILED' and caught.value.possible_effect is False
    assert productive_calls(state) == [] and state.mcp.effects == []
    assert state.checkpoint.saved == []


@pytest.mark.parametrize('operation', OPS)
@pytest.mark.parametrize('cut', ['lost_response', 'save_result'])
@pytest.mark.parametrize('creation_state', ['created', 'pending_approval'])
def test_restart_after_commit_recovers_original_without_another_creation(state, operation, cut, creation_state):
    state.mcp.creation_state = creation_state
    if cut == 'lost_response':
        state.mcp.creation_fault = 'after'
    else:
        state.checkpoint.fail_state = 'confirmed'
    with pytest.raises(ConnectionError) as caught:
        state.flow.submit(operation, 'durable:request', arguments(operation))
    assert caught.value.possible_effect is True
    assert state.checkpoint.last['state'] == 'uncertain'
    reopened = state.reopen(state.checkpoint.last)
    result = reopened.submit(operation, 'durable:request', arguments(operation))
    assert result['state'] == creation_state
    if creation_state == 'created':
        assert result['request_receipt']['resource_id'] in ('message-1', 'handoff-1')
    else:
        assert result['approval_id'] == 'approval-1' and result['request_receipt']['resource_id'] is None
    assert len(productive_calls(state)) == len(state.mcp.effects) == 1
    assert state.checkpoint.last['state'] == 'confirmed'


@pytest.mark.parametrize('method', ['wait', 'wait_request'])
@pytest.mark.parametrize('timeout', [float('nan'), float('inf'), -1, True, 86401, '2', None])
def test_observer_rejects_unbounded_or_invalid_deadline_before_network(state, method, timeout):
    with pytest.raises(ConnectionError) as error:
        getattr(state.flow, method)('handoff-1' if method == 'wait' else {}, timeout=timeout)
    assert error.value.code == 'OBSERVATION_TIMEOUT_INVALID'
    assert state.mcp.calls == []


@pytest.mark.parametrize('cursor', [True, -1, '3', None])
def test_observer_refuses_invalid_initial_cursor(state, cursor):
    state.mcp.cursor = cursor
    with pytest.raises(ConnectionError) as error:
        state.flow.wait('handoff-1', timeout=1)
    assert error.value.code == 'EVENT_CURSOR_UNCONFIRMED'
    assert not any(name == 'event_wait' for name, _, _ in state.mcp.calls)


@pytest.mark.parametrize('operation', OPS)
def test_not_found_within_original_window_retries_exact_saved_identity(state, operation):
    state.mcp.creation_fault = 'before'
    with pytest.raises(ConnectionError):
        state.flow.submit(operation, 'durable:request', arguments(operation))
    saved = state.checkpoint.last
    state.clock.sleep(60)
    result = state.reopen(saved).submit(operation, 'durable:request', arguments(operation))
    assert result['state'] == 'created' and len(state.mcp.effects) == 1
    assert len(productive_calls(state)) == 2
    assert {args['client_request_id'] for _, args in productive_calls(state)} == {'durable:request'}
    assert state.checkpoint.last['server_deadline'] == saved['server_deadline']
    assert state.checkpoint.last['local_deadline'] == saved['local_deadline']


@pytest.mark.parametrize('operation', OPS)
@pytest.mark.parametrize('change', ['content', 'target', 'trace', 'session'])
def test_replay_conflicts_before_network_when_content_target_or_context_changes(state, operation, change):
    original = arguments(operation)
    state.flow.submit(operation, 'durable:request', original)
    changed = deepcopy(original)
    if change == 'content':
        changed['body' if operation == 'message_create' else 'payload'] = 'Different content'
    elif change == 'target':
        changed['target']['agent_id'] = 'somebody-else'
    elif change == 'trace':
        changed['trace_id'] = 'trace-changed'
    else:
        changed['from_session_id' if operation == 'message_create' else 'session_id'] = 'other-session'
    before = deepcopy(state.mcp.calls)
    with pytest.raises(ConnectionError) as caught:
        state.reopen(state.checkpoint.last).submit(operation, 'durable:request', changed)
    assert caught.value.code == 'REQUEST_CONFLICT'
    assert state.mcp.calls == before


@pytest.mark.parametrize('operation', OPS)
def test_checkpoint_keeps_only_hash_and_verified_context_not_content_or_secret(state, operation):
    original = arguments(operation)
    state.flow.submit(operation, 'durable:request', original)
    serialized = json.dumps(state.checkpoint.saved)
    assert CONTENT not in serialized and SECRET not in serialized and 'session_secret' not in serialized
    assert state.checkpoint.last['context'] == {
        'from_session_id' if operation == 'message_create' else 'session_id': 'session-original'}
    # Authentication material is not semantic content. A renewed proof does not
    # overwrite the saved origin or require another productive send.
    result = state.reopen(state.checkpoint.last).submit(operation, 'durable:request',
                                                      original | {'session_secret': 'new-proof'})
    assert result['state'] == 'created' and len(productive_calls(state)) == 1


@pytest.mark.parametrize('change', ['missing_observed_at', 'invalid_observed_at', 'legacy_revision', 'retention'])
def test_old_or_unconfirmed_server_contract_refuses_before_checkpoint_and_creation(state, change):
    def mutate(discovery):
        contract = discovery['info']['coordination_requests']
        if change == 'missing_observed_at':
            contract.pop('observed_at')
        elif change == 'invalid_observed_at':
            contract['observed_at'] = '2026-11-06T12:00:00'
        elif change == 'legacy_revision':
            contract['revision'] = 0
        else:
            contract['retention_days'] = '30'
    state.mcp.discovery_change = mutate
    with pytest.raises(ConnectionError) as caught:
        state.flow.submit('message_create', 'durable:request', arguments('message_create'))
    assert caught.value.code == 'SERVER_UPGRADE_REQUIRED'
    assert state.checkpoint.saved == [] and productive_calls(state) == []


@pytest.mark.parametrize('field,value', [
    ('server_id', 'different-server'), ('actor_agent_id', 'somebody-else'), ('workspace_id', 'elsewhere'),
    ('operation', 'handoff_create'), ('client_request_id', 'different-request'),
    ('created_at', 'not-a-date'), ('created_at', '2026-11-06T12:00:00'),
    ('created_at', '2026-11-06T12:00:00-03:00'), ('created_at', None),
    ('expires_at', '2026-12-07T14:00:00+00:00'), ('state', 'unknown'),
    ('unexpected_private_field', SECRET),
])
def test_invalid_receipt_scope_and_timestamps_never_become_a_confirmed_checkpoint(state, field, value):
    state.mcp.receipt_change = lambda receipt: receipt.update({field: value})
    with pytest.raises(ConnectionError) as caught:
        state.flow.submit('message_create', 'durable:request', arguments('message_create'))
    assert caught.value.code == 'REQUEST_RESULT_UNCONFIRMED' and caught.value.possible_effect
    assert state.checkpoint.last['state'] == 'uncertain' and 'receipt' not in state.checkpoint.last
    assert len(productive_calls(state)) == 1


def test_created_receipt_requires_resource_reference(state):
    state.mcp.receipt_change = lambda receipt: receipt.update(resource_id=None, approval_id='approval-only')
    with pytest.raises(ConnectionError) as caught:
        state.flow.submit('message_create', 'durable:request', arguments('message_create'))
    assert caught.value.code == 'REQUEST_RESULT_UNCONFIRMED'


@pytest.mark.parametrize('action', ['submit', 'inspect'])
def test_missing_previously_confirmed_receipt_is_uncertain_and_never_recreated(state, action):
    state.flow.submit('message_create', 'durable:request', arguments('message_create'))
    state.mcp.receipts.clear()
    flow = state.reopen(state.checkpoint.last)
    with pytest.raises(ConnectionError) as caught:
        if action == 'submit':
            flow.submit('message_create', 'durable:request', arguments('message_create'))
        else:
            flow.inspect('message_create', 'durable:request')
    assert caught.value.code == 'REQUEST_RECEIPT_MISSING' and caught.value.possible_effect
    assert len(productive_calls(state)) == 1


@pytest.mark.parametrize('clock', ['local', 'server'])
@pytest.mark.parametrize('days', [30, 31])
def test_not_found_after_original_local_or_server_deadline_refuses_replay(state, clock, days):
    state.mcp.creation_fault = 'before'
    with pytest.raises(ConnectionError):
        state.flow.submit('message_create', 'durable:request', arguments('message_create'))
    setattr(state.clock, clock, getattr(state.clock, clock) + timedelta(days=days))
    with pytest.raises(ConnectionError) as caught:
        state.reopen(state.checkpoint.last).submit('message_create', 'durable:request', arguments('message_create'))
    assert caught.value.code == 'REQUEST_WINDOW_EXPIRED'
    assert len(productive_calls(state)) == 1 and state.mcp.effects == []


@pytest.mark.parametrize('clock', ['local', 'server'])
def test_clock_regression_refuses_replay_before_recovery_or_creation(state, clock):
    state.mcp.creation_fault = 'before'
    with pytest.raises(ConnectionError):
        state.flow.submit('message_create', 'durable:request', arguments('message_create'))
    setattr(state.clock, clock, getattr(state.clock, clock) - timedelta(seconds=1))
    with pytest.raises(ConnectionError) as caught:
        state.reopen(state.checkpoint.last).submit('message_create', 'durable:request', arguments('message_create'))
    assert caught.value.code == 'REQUEST_CLOCK_CHANGED'
    assert len(productive_calls(state)) == 1
    assert not any(tool == 'coordination_request_get' for tool, _, _ in state.mcp.calls)


def test_retained_expired_receipt_can_be_inspected_without_replay(state):
    state.flow.submit('message_create', 'durable:request', arguments('message_create'))
    state.clock.sleep(31 * 86400)
    flow = state.reopen(state.checkpoint.last)
    assert flow.inspect('message_create', 'durable:request')['state'] == 'expired'
    assert flow.submit('message_create', 'durable:request', arguments('message_create'))['state'] == 'expired'
    assert len(productive_calls(state)) == 1


def test_receipt_recovery_never_moves_original_deadline_or_resource(state):
    state.flow.submit('message_create', 'durable:request', arguments('message_create'))
    def move(receipt):
        receipt['created_at'] = (datetime.fromisoformat(receipt['created_at']) + timedelta(seconds=1)).isoformat()
        receipt['expires_at'] = (datetime.fromisoformat(receipt['expires_at']) + timedelta(seconds=1)).isoformat()
    state.mcp.receipt_change = move
    with pytest.raises(ConnectionError) as caught:
        state.reopen(state.checkpoint.last).inspect('message_create', 'durable:request')
    assert caught.value.code == 'REQUEST_RESULT_UNCONFIRMED'
    assert len(productive_calls(state)) == 1


def test_wait_captures_cursor_before_snapshot_and_detects_existing_completion(state):
    state.mcp.handoffs[0]['status'] = 'COMPLETED'
    state.mcp.handoffs[0]['result'] = CONTENT
    result = state.flow.wait('handoff-1', timeout=10)
    assert result['state'] == 'completed' and result['exit_code'] == 0
    assert [tool for tool, _, _ in state.mcp.calls] == ['discover', 'event_cursor', 'handoff_get']
    assert state.checkpoint.saved == []


def test_wait_rereads_canonical_handoff_even_when_no_event_is_visible(state):
    state.mcp.handoffs.append(dict(state.mcp.handoffs[0], status='COMPLETED'))
    result = state.flow.wait('handoff-1', timeout=40)
    assert result['state'] == 'completed'
    assert [tool for tool, _, _ in state.mcp.calls] == [
        'discover', 'event_cursor', 'handoff_get', 'event_wait', 'handoff_get']
    for tool, args, timeout in state.mcp.calls[1:]:
        assert args['passive'] is True and args['workspace_id'] == SCOPE['workspace_id']
        assert args['agent_id'] == SCOPE['agent_id']
        if tool == 'event_wait':
            assert args['filters'] == {'handoff_id': 'handoff-1'}
            assert args['cursor'] == 7 and args['timeout_seconds'] <= 30 and timeout <= 35
    assert productive_calls(state) == []


@pytest.mark.parametrize('status', ['OPEN', 'CLAIMED', 'VERIFYING'])
def test_wait_timeout_keeps_nonterminal_work_and_never_cancels_or_creates(state, status):
    state.mcp.handoffs[0]['status'] = status
    result = state.flow.wait('handoff-1', timeout=.25)
    assert result['state'] == 'timed_out' and result['exit_code'] == 4
    assert result['handoff']['status'] == status and state.clock.elapsed == .25
    assert {tool for tool, _, _ in state.mcp.calls} <= {'discover', 'event_cursor', 'handoff_get', 'event_wait'}
    assert state.checkpoint.saved == []


@pytest.mark.parametrize('failure', [KeyboardInterrupt(), ConnectionError('SERVER_UNREACHABLE', 'Read unavailable')])
def test_wait_interruption_and_read_errors_do_not_cancel_or_recreate(state, failure):
    state.mcp.wait_failure = failure
    with pytest.raises(type(failure)):
        state.flow.wait('handoff-1', timeout=5)
    assert {tool for tool, _, _ in state.mcp.calls} <= {'discover', 'event_cursor', 'handoff_get', 'event_wait'}
    assert state.checkpoint.saved == [] and state.mcp.effects == []


def test_wait_rejects_a_cursor_regression_without_mutation(state):
    state.mcp.following_cursor = 6
    with pytest.raises(ConnectionError) as caught:
        state.flow.wait('handoff-1', timeout=5)
    assert caught.value.code == 'EVENT_CURSOR_UNCONFIRMED'
    assert state.mcp.effects == []


def test_wait_requires_the_advertised_passive_contract_before_observing(state):
    state.mcp.discovery_change = lambda discovery: discovery['info']['coordination_observation'].update(passive=False)
    with pytest.raises(ConnectionError) as caught:
        state.flow.wait('handoff-1', timeout=5)
    assert caught.value.code == 'SERVER_UPGRADE_REQUIRED'
    assert state.mcp.calls == [('discover', {}, None)]


@pytest.mark.parametrize('transition,expected', [('created', 'completed'), ('rejected', 'rejected')])
def test_pending_approval_wait_follows_original_request_without_approving_or_resending(state, transition, expected):
    state.mcp.creation_state = 'pending_approval'
    pending = state.flow.submit('handoff_create', 'durable:request', arguments('handoff_create'))
    assert pending['approval_id'] == 'approval-1'
    state.mcp.lookup_transition = transition
    state.mcp.handoffs[0]['status'] = 'COMPLETED'
    result = state.flow.wait_request(pending, timeout=5)
    assert result['state'] == expected
    assert result['exit_code'] == (0 if expected == 'completed' else 3)
    assert len(productive_calls(state)) == len(state.mcp.effects) == 1
    assert not any('decide' in tool or 'approve' in tool or 'cancel' in tool for tool, _, _ in state.mcp.calls)


def test_pending_approval_timeout_preserves_request_and_approval_ids(state):
    state.mcp.creation_state = 'pending_approval'
    pending = state.flow.submit('handoff_create', 'durable:request', arguments('handoff_create'))
    result = state.flow.wait_request(pending, timeout=1)
    assert result['state'] == 'timed_out' and result['exit_code'] == 4
    assert result['client_request_id'] == 'durable:request' and result['approval_id'] == 'approval-1'
    assert len(productive_calls(state)) == 1


@pytest.mark.parametrize('interrupted', [True, False])
def test_pending_approval_wait_interruption_or_lookup_error_keeps_original_request(state, monkeypatch, interrupted):
    state.mcp.creation_state = 'pending_approval'
    pending = state.flow.submit('handoff_create', 'durable:request', arguments('handoff_create'))
    saved = state.checkpoint.last
    failure = KeyboardInterrupt() if interrupted else ConnectionError('SERVER_UNREACHABLE', 'Read unavailable')
    original = state.mcp.call

    def fail_lookup(tool, arguments, **kwargs):
        if tool == 'coordination_request_get':
            raise failure
        return original(tool, arguments, **kwargs)

    monkeypatch.setattr(state.mcp, 'call', fail_lookup)
    with pytest.raises(type(failure)):
        state.flow.wait_request(pending, timeout=5)
    assert state.checkpoint.last == saved
    assert len(productive_calls(state)) == len(state.mcp.effects) == 1


def test_runtime_contract_validation_survives_optimized_python_subprocess():
    from pathlib import Path
    import subprocess
    import sys
    import okto_nexus

    # Import the same source or installed package as this test, even when the
    # campaign is running outside the checkout. No credentials or services.
    script = 'import sys\nsys.path.insert(0, ' + repr(str(Path(okto_nexus.__file__).resolve().parent.parent)) + ')\n' + '''
from copy import deepcopy
from types import SimpleNamespace
import json
from okto_nexus.application.terminal_coordination import TerminalCoordination
from okto_nexus.application.terminal_connection import ConnectionError

scope = dict(server_id="server", agent_id="caller", workspace_id="workspace")
doc = dict(revision=1, scope=scope, operation="message_create", client_request_id="request",
    intent_hash="a" * 64, state="uncertain", context={},
    local_first="2026-11-06T12:00:00+00:00", local_last="2026-11-06T12:00:00+00:00",
    local_deadline="2026-12-06T12:00:00+00:00", server_first="2026-11-06T12:00:00+00:00",
    server_last="2026-11-06T12:00:00+00:00", server_deadline="2026-12-06T12:00:00+00:00")
codes = []
def check(action):
    try:
        action()
    except ConnectionError as error:
        codes.append(error.code)
    else:
        raise RuntimeError("Optimized Python accepted invalid runtime input")

invalid = deepcopy(doc)
invalid["local_deadline"] = "2027-12-06T12:00:00+00:00"
check(lambda: TerminalCoordination(None, scope, lambda value: None, invalid))
mcp = SimpleNamespace(discover=lambda: {"info": {"coordination_requests": {
    "observed_at": "2026-11-06T12:00:00+00:00"}}, "schemas": {}})
flow = TerminalCoordination(mcp, scope, lambda value: None, doc)
check(flow.discover)
receipt = dict(server_id="server", actor_agent_id="caller", workspace_id="workspace",
    operation="message_create", client_request_id="request", state="created", resource_id="message-original",
    approval_id=None, created_at="2026-11-06T12:00:00+00:00", expires_at="2026-12-06T12:00:00+00:00")
flow.document["receipt"] = deepcopy(receipt)
receipt["resource_id"] = "message-substituted"
check(lambda: flow._accept(dict(status="created", workspace_id="workspace", request_receipt=receipt),
                          "message_create", "request"))
print(json.dumps(dict(optimized=not __debug__, codes=codes)))
'''
    result = subprocess.run([sys.executable, '-I', '-O', '-c', script],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == dict(optimized=True, codes=[
        'CHECKPOINT_INVALID', 'SERVER_UPGRADE_REQUIRED', 'REQUEST_RESULT_UNCONFIRMED'])


@pytest.mark.parametrize('status', ['OPEN', 'VERIFYING'])
def test_delivery_read_and_native_idle_events_never_complete_handoff_wait(state, monkeypatch, status):
    state.mcp.handoffs[0]['status'] = status
    state.mcp.following_cursor = 10
    original = state.mcp.call
    observed = []

    def transport(tool, arguments, **kwargs):
        page = original(tool, arguments, **kwargs)
        if tool == 'event_wait':
            page['events'] = [
                dict(event_id=8, type='message.delivered', payload=dict(handoff_id='handoff-1', message_id='notice')),
                dict(event_id=9, type='message.read', payload=dict(handoff_id='handoff-1', message_id='notice')),
                dict(event_id=10, type='runtime.state', payload=dict(handoff_id='handoff-1',
                    source='native', activity='idle')),
            ]
            observed.extend(page['events'])
        return page

    monkeypatch.setattr(state.mcp, 'call', transport)
    result = state.flow.wait('handoff-1', timeout=1)
    assert len(observed) == 3
    assert result['state'] == 'timed_out' and result['exit_code'] == 4
    assert result['handoff']['status'] == status
    assert [tool for tool, _, _ in state.mcp.calls].count('handoff_get') == 2
    assert productive_calls(state) == [] and state.checkpoint.saved == []
