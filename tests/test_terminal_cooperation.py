"""Cooperation consent, canonical proof and crash recovery without providers."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus.application.terminal_cooperation import TerminalCooperation


SCOPE = dict(origin='https://nexus.example', server_id='server', agent_id='sender', workspace_id='workspace')
BINDING = 'a' * 64
OPS = ('message_create', 'handoff_create')
SECRET = 'synthetic-private-session-proof'


class Clock:
    def __init__(self):
        self.local = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
        self.server = self.local + timedelta(hours=2)
        self.elapsed = 0

    def sleep(self, seconds):
        self.elapsed += seconds
        self.local += timedelta(seconds=seconds)
        self.server += timedelta(seconds=seconds)


class Journal:
    def __init__(self):
        self.saved = []
        self.fail = None

    def save(self, value):
        if self.fail and self.fail(value):
            self.fail = None
            raise OSError('synthetic persistence failure')
        self.saved.append(deepcopy(value))

    @property
    def last(self):
        return deepcopy(self.saved[-1]) if self.saved else None


class Requests(Journal):
    def load(self, operation, identity):
        for value in reversed(self.saved):
            if (value['operation'], value['client_request_id']) == (operation, identity):
                return deepcopy(value)
        return None


class MCP:
    def __init__(self, clock, journal, requests):
        self.clock, self.journal, self.requests = clock, journal, requests
        self.calls, self.effects, self.receipts = [], [], {}
        self.replies = []
        self.handoff = dict(handoff_id='handoff-1', workspace_id=SCOPE['workspace_id'], from_agent_id=SCOPE['agent_id'],
            target=dict(strategy='direct', agent_id='peer'), status='OPEN', claimed_by=None, claim_epoch=0, result=None)
        self.discovery_change = None
        self.fault = None
        self.creation_state = 'created'
        self.wait_hook = None
        self.wait_failure = None
        self.status_failure = None
        self.lookup_hook = None
        self.cursor, self.next_cursor = 10, 10
        self.events = []
        self.truncated = False
        self.deliveries = [dict(recipient='peer', status='unread', attempts=0, read_at=None)]

    def discover(self):
        self.calls.append(('discover', {}, None))
        schemas = {tool: dict(properties={field: {} for field in fields}) for tool, fields in {
            'message_create': ('client_request_id', 'workspace_id', 'from_agent_id'),
            'handoff_create': ('client_request_id', 'workspace_id', 'from_agent_id'),
            'coordination_request_get': ('workspace_id', 'operation', 'client_request_id'),
            'handoff_get': ('passive', 'workspace_id', 'agent_id'),
            'event_cursor': ('passive', 'workspace_id', 'agent_id'),
            'event_wait': ('passive', 'workspace_id', 'agent_id'),
            'message_status': ('message_id', 'include_replies'),
        }.items()}
        info = dict(coordination_requests=dict(revision=1, retention_days=30, operations=list(OPS),
                recovery_tool='coordination_request_get', response='references', observed_at=self.clock.server.isoformat()),
            coordination_observation=dict(revision=1, passive=True, workspace_selector=True),
            coordination_cooperation=dict(revision=1, reply_tool='message_status', direct_replies=True, authority_provenance=True))
        discovery = dict(info=info, schemas=schemas)
        if self.discovery_change:
            self.discovery_change(discovery)
        return discovery

    @staticmethod
    def response(receipt):
        value = dict(status=receipt['state'], workspace_id=receipt['workspace_id'], request_receipt=deepcopy(receipt))
        if receipt['resource_id']:
            value['message_id' if receipt['operation'] == 'message_create' else 'handoff_id'] = receipt['resource_id']
        return value

    def call(self, tool, arguments, *, timeout=None):
        self.calls.append((tool, deepcopy(arguments), timeout))
        if tool in OPS:
            phase = 'exchange' if tool == 'message_create' else 'handoff'
            doc = self.journal.last
            assert doc['consents'][phase] == doc['reviews'][phase]
            assert self.requests.load(tool, arguments['client_request_id'])['state'] == 'uncertain'
            fault, self.fault = self.fault, None
            if fault == 'before':
                raise ConnectionError('OUTCOME_UNKNOWN', 'Synthetic lost request', possible_effect=True)
            key = tool, arguments['client_request_id']
            if key not in self.receipts:
                self.effects.append(key)
                self.receipts[key] = dict(server_id=SCOPE['server_id'], actor_agent_id=SCOPE['agent_id'],
                    workspace_id=SCOPE['workspace_id'], operation=tool, client_request_id=key[1], state=self.creation_state,
                    resource_id=('message-1' if phase == 'exchange' else 'handoff-1') if self.creation_state == 'created' else None,
                    approval_id='approval-1' if self.creation_state == 'pending_approval' else None,
                    created_at=self.clock.server.isoformat(), expires_at=(self.clock.server + timedelta(days=30)).isoformat())
            if fault == 'after':
                raise ConnectionError('OUTCOME_UNKNOWN', 'Synthetic lost response', possible_effect=True)
            return self.response(self.receipts[key])
        if tool == 'coordination_request_get':
            key = arguments['operation'], arguments['client_request_id']
            if key not in self.receipts:
                raise ConnectionError('NOT_FOUND', 'Synthetic absence')
            if self.lookup_hook:
                self.lookup_hook(key)
            return self.response(self.receipts[key])
        if tool == 'message_status':
            if self.status_failure:
                raise self.status_failure
            return dict(message_id='message-1', deliveries=deepcopy(self.deliveries), count=len(self.deliveries),
                replies=deepcopy(self.replies), replies_truncated=self.truncated)
        if tool == 'event_cursor':
            return dict(cursor=self.cursor)
        if tool == 'handoff_get':
            return deepcopy(self.handoff)
        if tool == 'event_wait':
            if self.wait_failure:
                raise self.wait_failure
            self.clock.sleep(arguments['timeout_seconds'])
            if self.wait_hook:
                hook, self.wait_hook = self.wait_hook, None
                hook()
            return dict(events=deepcopy(self.events), next_cursor=self.next_cursor, timed_out=True)
        raise AssertionError('Unexpected call: ' + tool)

    def reply(self, **changes):
        value = dict(message_id='reply-1', parent_message_id='message-1', workspace_id=SCOPE['workspace_id'],
            from_agent_id='peer', target=dict(strategy='direct', agent_id=SCOPE['agent_id']),
            created_at=self.clock.server.isoformat(), delivery_status='unread', read_at=None,
            authority_kind='coordination_request', runtime_outcome=None)
        value.update(changes)
        return value

    def complete(self, **changes):
        self.handoff.update(status='COMPLETED', claimed_by='peer', claim_epoch=1, result='private result not a checkpoint')
        self.handoff.update(changes)


@pytest.fixture
def state():
    clock, journal, requests = Clock(), Journal(), Requests()
    mcp = MCP(clock, journal, requests)

    def reopen():
        return TerminalCooperation(mcp, SCOPE, journal.save, requests, journal.last,
            now=lambda: clock.local, monotonic=lambda: clock.elapsed, sleep=clock.sleep)

    return SimpleNamespace(clock=clock, journal=journal, requests=requests, mcp=mcp, reopen=reopen, flow=reopen())


def send_exchange(state, *, session_id=None):
    review = state.flow.review_exchange('peer', BINDING, session_id)
    return state.flow.send_exchange(review['review_revision'])


def handoff_review(state):
    send_exchange(state)
    state.mcp.replies = [state.mcp.reply()]
    return state.flow.review_handoff()


def send_handoff(state):
    review = handoff_review(state)
    return state.flow.send_handoff(review['review_revision'])


def creates(state):
    return [(tool, args) for tool, args, _ in state.mcp.calls if tool in OPS]


def test_review_status_and_existing_plan_are_offline_and_reference_only(state):
    review = state.flow.review_exchange('peer', BINDING, 'explicit-session')
    snapshot = deepcopy(state.journal.saved)
    assert state.mcp.calls == []
    assert state.reopen().status() == state.flow.status()
    assert state.reopen().review_exchange('peer', BINDING, 'explicit-session') == review
    assert state.journal.saved == snapshot and state.mcp.calls == []
    encoded = json.dumps(state.journal.last)
    assert 'body' not in encoded and 'payload' not in encoded and 'secret' not in encoded and 'objective' not in encoded
    assert review['request_ids']['message_create'] != review['request_ids']['handoff_create']
    assert review['qualification'] == 'identities_only'
    assert all(check['status'] == 'UNKNOWN' for check in review['checks'].values())
    assert 'cost' in review['review']['arguments']['body']
    assert 'parent_message_id' in review['review']['arguments']['body']
    assert review['smoke_id'] + ':reply' in review['review']['arguments']['body']
    assert 'NEXUS_CONNECTION_OK' not in json.dumps(review)


@pytest.mark.parametrize('change', [dict(peer='another'), dict(profile_binding='b' * 64), dict(session_id='another')])
def test_existing_attempt_cannot_change_peer_profile_or_session(state, change):
    state.flow.review_exchange('peer', BINDING)
    with pytest.raises(ConnectionError) as error:
        state.reopen().review_exchange(**(dict(peer='peer', profile_binding=BINDING, session_id=None) | change))
    assert error.value.code == 'REQUEST_CONFLICT' and state.mcp.calls == []


@pytest.mark.parametrize('approval', [None, '', 'wrong'])
def test_no_productive_action_without_exact_phase_consent(state, approval):
    state.flow.review_exchange('peer', BINDING)
    with pytest.raises(ConnectionError) as error:
        state.flow.send_exchange(approval)
    assert error.value.code == 'REVIEW_REQUIRED' and state.mcp.calls == []
    assert state.journal.last['consents']['exchange'] is None


def test_exchange_consent_never_authorizes_handoff(state):
    review = handoff_review(state)
    assert review['reviews']['exchange'] != review['reviews']['handoff']
    before = len(creates(state))
    with pytest.raises(ConnectionError) as error:
        state.flow.send_handoff(review['reviews']['exchange'])
    assert error.value.code == 'REVIEW_REQUIRED' and len(creates(state)) == before == 1
    assert state.journal.last['consents']['handoff'] is None


@pytest.mark.parametrize('phase', ['exchange', 'handoff'])
@pytest.mark.parametrize('cut', ['before', 'after', 'requests_result', 'journal_result'])
def test_crash_recovery_preserves_one_effect_and_same_ids(state, phase, cut):
    review = state.flow.review_exchange('peer', BINDING) if phase == 'exchange' else handoff_review(state)
    operation = 'message_create' if phase == 'exchange' else 'handoff_create'
    if cut in ('before', 'after'):
        state.mcp.fault = cut
    elif cut == 'requests_result':
        state.requests.fail = lambda value: value['state'] == 'confirmed' and value['operation'] == operation
    else:
        state.journal.fail = lambda value: value['receipts'][phase] is not None
    with pytest.raises(ConnectionError) as error:
        getattr(state.flow, 'send_' + phase)(review['review_revision'])
    assert error.value.possible_effect is True
    original_ids = deepcopy(state.journal.last['request_ids'])
    restored = state.reopen()
    result = getattr(restored, 'send_' + phase)(review['review_revision'])
    assert result['request_ids'] == original_ids
    assert len([effect for effect in state.mcp.effects if effect[0] == operation]) == 1
    transmissions = [args for tool, args in creates(state) if tool == operation]
    assert {args['client_request_id'] for args in transmissions} == {original_ids[operation]}
    assert len(transmissions) == (2 if cut == 'before' else 1)


@pytest.mark.parametrize('stage', ['review', 'consent'])
def test_journal_failure_before_send_has_zero_productive_calls(state, stage):
    if stage == 'review':
        state.journal.fail = lambda value: True
        def call():
            return state.flow.review_exchange('peer', BINDING)
    else:
        review = state.flow.review_exchange('peer', BINDING)
        state.journal.fail = lambda value: value['consents']['exchange'] is not None
        def call():
            return state.flow.send_exchange(review['review_revision'])
    with pytest.raises(ConnectionError) as error:
        call()
    assert error.value.code == 'CHECKPOINT_WRITE_FAILED' and error.value.possible_effect is False
    assert creates(state) == []


@pytest.mark.parametrize('change', [
    lambda d: d['info'].pop('coordination_cooperation'),
    lambda d: d['info']['coordination_cooperation'].update(authority_provenance=False),
    lambda d: d['info']['coordination_cooperation'].update(direct_replies=False),
    lambda d: d['info']['coordination_cooperation'].update(revision=True),
    lambda d: d['schemas']['message_status']['properties'].pop('include_replies'),
    lambda d: d['info']['coordination_observation'].update(passive=False),
])
def test_old_or_incomplete_discovery_refuses_before_creation(state, change):
    review = state.flow.review_exchange('peer', BINDING)
    state.mcp.discovery_change = change
    with pytest.raises(ConnectionError) as error:
        state.flow.send_exchange(review['review_revision'])
    assert error.value.code == 'SERVER_UPGRADE_REQUIRED' and creates(state) == []


@pytest.mark.parametrize('change', [
    dict(from_agent_id='stranger'), dict(parent_message_id='other-message'), dict(workspace_id='other-workspace'),
    dict(target=dict(strategy='broadcast')), dict(target=dict(strategy='direct', agent_id='other')),
    dict(authority_kind='unconfirmed'), dict(authority_kind='runtime_result', runtime_outcome='failed'),
    dict(authority_kind='runtime_result', runtime_outcome='interrupted'),
    dict(authority_kind='runtime_result', runtime_outcome=None), dict(delivery_status=None),
])
def test_noncorrelated_or_unproven_reply_never_proves_exchange(state, change):
    send_exchange(state)
    state.mcp.replies = [state.mcp.reply(**change)]
    state.mcp.events = [dict(type='message.created', payload=dict(body='NEXUS_CONNECTION_OK'))]
    result = state.flow.observe(timeout=1)
    assert result['state'] == 'timed_out' and result['exit_code'] == 4
    assert result['checks']['coordination_participation']['status'] == 'UNKNOWN'
    assert state.journal.last['evidence']['exchange'] is None and len(creates(state)) == 1
    with pytest.raises(ConnectionError):
        state.flow.review_handoff()


@pytest.mark.parametrize('authority', ['coordination_request', 'runtime_result'])
@pytest.mark.parametrize('delivery', ['unread', 'delivered', 'read'])
def test_canonical_reply_proves_exchange_even_when_already_read(state, authority, delivery):
    send_exchange(state)
    state.mcp.replies = [state.mcp.reply(authority_kind=authority,
        runtime_outcome='completed' if authority == 'runtime_result' else None,
        delivery_status=delivery, read_at=state.clock.server.isoformat() if delivery == 'read' else None)]
    result = state.flow.observe(timeout=0)
    assert result['state'] == 'exchange_proven' and result['exit_code'] == 0
    assert result['checks']['coordination_participation']['status'] == 'PASS'
    assert result['checks']['handoff_test']['status'] == 'UNKNOWN'
    calls = [name for name, _, _ in state.mcp.calls]
    assert calls.index('event_cursor') < calls.index('message_status')
    assert 'handoff_create' not in calls and 'inbox_pull' not in calls and 'inbox_ack' not in calls


def test_empty_event_page_still_rereads_canonical_reply(state):
    send_exchange(state)
    state.mcp.wait_hook = lambda: state.mcp.replies.append(state.mcp.reply())
    result = state.flow.observe(timeout=31)
    assert result['state'] == 'exchange_proven'
    waits = [(args, timeout) for name, args, timeout in state.mcp.calls if name == 'event_wait']
    assert waits and all(args['passive'] and args['timeout_seconds'] <= 30 and timeout <= 35 for args, timeout in waits)
    assert len(creates(state)) == 1


@pytest.mark.parametrize('deliveries', [[], [dict(recipient='stranger', status='read')],
    [dict(recipient='peer', status='nonexistent')]])
def test_original_message_must_have_a_canonical_delivery_to_the_peer(state, deliveries):
    send_exchange(state)
    state.mcp.replies = [state.mcp.reply()]
    state.mcp.deliveries = deliveries
    result = state.flow.observe(timeout=0)
    assert result['checks']['coordination_participation']['status'] == 'UNKNOWN'
    assert result['exit_code'] == 4 and state.journal.last['evidence']['exchange'] is None


@pytest.mark.parametrize('change', [dict(created_at='invalid'), dict(read_at='invalid'),
    dict(created_at='2026-11-05T00:00:00+00:00'), dict(delivery_status='read', read_at=None)])
def test_malformed_canonical_reply_metadata_is_not_accepted(state, change):
    send_exchange(state)
    state.mcp.replies = [state.mcp.reply(**change)]
    with pytest.raises(ConnectionError) as error:
        state.flow.observe(timeout=0)
    assert error.value.code == 'REQUEST_RESULT_UNCONFIRMED'
    assert state.journal.last['evidence']['exchange'] is None


def test_current_reply_is_required_again_before_handoff_creation(state):
    review = handoff_review(state)
    state.mcp.replies = []
    with pytest.raises(ConnectionError) as error:
        state.flow.send_handoff(review['review_revision'])
    assert error.value.code == 'REVIEW_REQUIRED' and len(creates(state)) == 1
    assert state.journal.last['consents']['handoff'] is None


@pytest.mark.parametrize('change', [
    dict(handoff_id='other'), dict(workspace_id='other'), dict(from_agent_id='other'),
    dict(target=dict(strategy='broadcast')), dict(target=dict(strategy='direct', agent_id='other')),
    dict(claimed_by='other'), dict(claim_epoch=0), dict(claim_epoch=True), dict(result=None),
])
def test_completion_requires_exact_scope_peer_claim_and_result(state, change):
    send_handoff(state)
    state.mcp.complete(**change)
    with pytest.raises(ConnectionError) as error:
        state.flow.observe(timeout=0)
    assert error.value.code == 'HANDOFF_RESULT_UNCONFIRMED'
    assert state.journal.last['evidence']['handoff'] is None and len(creates(state)) == 2


def test_handoff_completion_is_canonical_and_result_is_never_persisted(state):
    send_handoff(state)
    state.mcp.complete()
    result = state.flow.observe(timeout=0)
    assert result['state'] == 'handoff_proven' and result['exit_code'] == 0
    assert all(check['status'] == 'PASS' for check in result['checks'].values())
    assert result['evidence']['handoff']['claim_epoch'] == 1
    encoded = json.dumps(state.journal.saved + state.requests.saved + [result])
    assert state.mcp.handoff['result'] not in encoded
    assert {name for name, _, _ in state.mcp.calls} <= {
        'discover', 'message_create', 'handoff_create', 'coordination_request_get', 'message_status',
        'handoff_get', 'event_cursor', 'event_wait'}


@pytest.mark.parametrize('missing', ['reply', 'message', 'receipt'])
def test_missing_exchange_evidence_does_not_block_observation_of_existing_handoff(state, missing):
    send_handoff(state)
    original_ids = state.journal.last['request_ids']
    if missing == 'reply':
        state.mcp.replies = []
    elif missing == 'message':
        state.mcp.status_failure = ConnectionError('NOT_FOUND', 'Synthetic pruned message')
    else:
        state.mcp.receipts.pop(('message_create', original_ids['message_create']))
    state.mcp.complete()
    result = state.reopen().observe(timeout=0)
    assert result['state'] == 'handoff_proven' and result['exit_code'] == 0
    assert result['checks']['coordination_participation']['status'] == 'UNKNOWN'
    assert result['checks']['handoff_test']['status'] == 'PASS'
    assert result['request_ids'] == original_ids and len(creates(state)) == 2


@pytest.mark.parametrize('phase', ['exchange', 'handoff'])
def test_pending_approval_remains_same_request_and_does_not_create_again(state, phase):
    review = state.flow.review_exchange('peer', BINDING) if phase == 'exchange' else handoff_review(state)
    state.mcp.creation_state = 'pending_approval'
    getattr(state.flow, 'send_' + phase)(review['review_revision'])
    result = state.reopen().observe(timeout=1)
    assert result['exit_code'] == 4
    assert result['receipts'][phase]['state'] == 'pending_approval'
    assert len(creates(state)) == (1 if phase == 'exchange' else 2)


@pytest.mark.parametrize('phase', ['exchange', 'handoff'])
def test_observer_recovers_approval_execution_and_proves_the_original_resource(state, phase):
    review = state.flow.review_exchange('peer', BINDING) if phase == 'exchange' else handoff_review(state)
    state.mcp.creation_state = 'pending_approval'
    getattr(state.flow, 'send_' + phase)(review['review_revision'])
    operation = 'message_create' if phase == 'exchange' else 'handoff_create'
    seen = 0

    def transition(key):
        nonlocal seen
        if key[0] == operation:
            seen += 1
            if seen == 2:
                state.mcp.receipts[key].update(state='created', resource_id='message-1' if phase == 'exchange' else 'handoff-1')
                if phase == 'exchange':
                    state.mcp.replies = [state.mcp.reply()]
                else:
                    state.mcp.complete()

    state.mcp.lookup_hook = transition
    result = state.reopen().observe(timeout=31)
    assert result['exit_code'] == 0
    assert result['state'] == ('exchange_proven' if phase == 'exchange' else 'handoff_proven')
    assert result['receipts'][phase]['approval_id'] == 'approval-1'
    assert result['receipts'][phase]['state'] == 'created'
    assert len(creates(state)) == (1 if phase == 'exchange' else 2)


@pytest.mark.parametrize('status', ['OPEN', 'VERIFYING'])
def test_delivered_read_native_idle_and_verifying_never_complete_handoff(state, status):
    send_handoff(state)
    state.mcp.handoff.update(status=status, claimed_by='peer', claim_epoch=1, result='NEXUS_CONNECTION_OK')
    state.mcp.events = [dict(type=event, payload=dict(handoff_id='handoff-1'))
        for event in ('message.delivered', 'message.read', 'runtime.idle')]
    result = state.flow.observe(timeout=1)
    assert result['state'] == 'timed_out' and result['exit_code'] == 4
    assert result['checks']['handoff_test']['status'] == 'UNKNOWN' and len(creates(state)) == 2


@pytest.mark.parametrize('phase', ['exchange', 'handoff'])
@pytest.mark.parametrize('failure', [KeyboardInterrupt(), ConnectionError('MCP_REQUEST_UNCONFIRMED', 'Synthetic failure')])
def test_wait_interruption_preserves_attempt_and_never_cancels_or_recreates(state, phase, failure):
    send_exchange(state) if phase == 'exchange' else send_handoff(state)
    original = state.journal.last['request_ids']
    state.mcp.wait_failure = failure
    with pytest.raises(type(failure)):
        state.flow.observe(timeout=1)
    assert state.reopen().status()['request_ids'] == original
    assert len(creates(state)) == (1 if phase == 'exchange' else 2)
    assert not any(name in ('handoff_cancel', 'handoff_claim', 'handoff_complete') for name, _, _ in state.mcp.calls)


def test_session_proof_only_crosses_productive_boundary_and_never_persists(state):
    review = state.flow.review_exchange('peer', BINDING, 'explicit-session')
    state.flow.send_exchange(review['review_revision'], session_secret=SECRET)
    state.mcp.replies = [state.mcp.reply()]
    review = state.flow.review_handoff()
    state.flow.send_handoff(review['review_revision'], session_secret=SECRET)
    assert all(args['session_secret'] == SECRET for _, args in creates(state))
    assert creates(state)[0][1]['from_session_id'] == creates(state)[1][1]['session_id'] == 'explicit-session'
    assert SECRET not in json.dumps(state.journal.saved + state.requests.saved + [state.flow.status()])


@pytest.mark.parametrize('cut', ['local', 'server'])
def test_unknown_request_outside_window_never_resends(state, cut):
    review = state.flow.review_exchange('peer', BINDING)
    state.mcp.fault = 'before'
    with pytest.raises(ConnectionError):
        state.flow.send_exchange(review['review_revision'])
    if cut == 'local':
        state.clock.local += timedelta(days=31)
    else:
        state.clock.server += timedelta(days=31)
    with pytest.raises(ConnectionError) as error:
        state.reopen().send_exchange(review['review_revision'])
    assert error.value.code == 'REQUEST_WINDOW_EXPIRED' and len(creates(state)) == 1


def test_receipt_disappearing_after_confirmation_never_recreates(state):
    review = state.flow.review_exchange('peer', BINDING)
    state.flow.send_exchange(review['review_revision'])
    state.mcp.receipts.clear()
    with pytest.raises(ConnectionError) as error:
        state.reopen().observe(timeout=0)
    assert error.value.code == 'REQUEST_RECEIPT_MISSING' and error.value.possible_effect
    assert len(creates(state)) == 1


def test_missing_request_file_does_not_reset_a_confirmed_request_window(state):
    review = state.flow.review_exchange('peer', BINDING)
    state.flow.send_exchange(review['review_revision'])
    state.requests.saved.clear()
    state.mcp.receipts.clear()
    state.clock.sleep(31 * 86400)
    with pytest.raises(ConnectionError) as error:
        state.reopen().send_exchange(review['review_revision'])
    assert error.value.code == 'REQUEST_RECEIPT_MISSING'
    assert len(creates(state)) == 1


@pytest.mark.parametrize('phase', ['exchange', 'handoff'])
@pytest.mark.parametrize('retained', [True, False])
def test_lost_response_and_missing_checkpoint_only_inspect_prior_consent(state, phase, retained):
    review = state.flow.review_exchange('peer', BINDING) if phase == 'exchange' else handoff_review(state)
    operation = 'message_create' if phase == 'exchange' else 'handoff_create'
    state.mcp.fault = 'after'
    with pytest.raises(ConnectionError):
        getattr(state.flow, 'send_' + phase)(review['review_revision'])
    original_ids = deepcopy(state.journal.last['request_ids'])
    assert state.journal.last['consents'][phase] == review['review_revision']
    assert state.journal.last['receipts'][phase] is None
    state.requests.saved[:] = [value for value in state.requests.saved if value['operation'] != operation]
    if not retained:
        state.clock.sleep(31 * 86400)
        state.mcp.receipts.pop((operation, original_ids[operation]))
    previous_creates = deepcopy(creates(state))
    restored = state.reopen()
    if retained:
        result = getattr(restored, 'send_' + phase)(review['review_revision'])
        assert result['receipts'][phase]['resource_id'] == ('message-1' if phase == 'exchange' else 'handoff-1')
        assert result['request_ids'] == original_ids
    else:
        with pytest.raises(ConnectionError) as error:
            getattr(restored, 'send_' + phase)(review['review_revision'])
        assert error.value.code == 'NOT_FOUND' and error.value.possible_effect is True
        assert 'do not recreate' in error.value.message
        assert state.journal.last['receipts'][phase] is None
    assert creates(state) == previous_creates
    assert state.requests.load(operation, original_ids[operation]) is None
    assert state.journal.last['request_ids'] == original_ids


@pytest.mark.parametrize('phase', ['exchange', 'handoff'])
def test_failed_request_checkpoint_after_consent_requires_inspection_on_restart(state, phase):
    review = state.flow.review_exchange('peer', BINDING) if phase == 'exchange' else handoff_review(state)
    operation = 'message_create' if phase == 'exchange' else 'handoff_create'
    state.requests.fail = lambda value: value['state'] == 'uncertain' and value['operation'] == operation
    previous_creates = deepcopy(creates(state))
    with pytest.raises(ConnectionError) as first:
        getattr(state.flow, 'send_' + phase)(review['review_revision'])
    assert first.value.code == 'CHECKPOINT_WRITE_FAILED' and first.value.possible_effect is False
    original_ids = deepcopy(state.journal.last['request_ids'])
    assert state.journal.last['consents'][phase] == review['review_revision']
    assert state.requests.load(operation, original_ids[operation]) is None
    with pytest.raises(ConnectionError) as resumed:
        getattr(state.reopen(), 'send_' + phase)(review['review_revision'])
    assert resumed.value.code == 'NOT_FOUND' and resumed.value.possible_effect is True
    assert creates(state) == previous_creates and state.journal.last['request_ids'] == original_ids


@pytest.mark.parametrize('phase', ['exchange', 'handoff'])
@pytest.mark.parametrize('receipt_state', ['resource_removed', 'expired'])
def test_current_terminal_negative_receipt_never_reuses_historical_pass(state, phase, receipt_state):
    send_exchange(state) if phase == 'exchange' else send_handoff(state)
    state.mcp.replies = [state.mcp.reply()]
    if phase == 'handoff':
        state.mcp.complete()
    state.flow.observe(timeout=0)
    historical = deepcopy(state.journal.last['evidence'])
    original_ids = deepcopy(state.journal.last['request_ids'])
    if receipt_state == 'expired':
        state.clock.sleep(31 * 86400)
        for receipt in state.mcp.receipts.values():
            receipt['state'] = 'expired'
    else:
        operation = 'message_create' if phase == 'exchange' else 'handoff_create'
        state.mcp.receipts[(operation, original_ids[operation])]['state'] = receipt_state
    previous_creates = deepcopy(creates(state))
    restored = state.reopen()
    result = restored.observe(timeout=0)
    check = 'coordination_participation' if phase == 'exchange' else 'handoff_test'
    assert result['state'] == receipt_state and result['exit_code'] == 3 and result['historical'] is False
    assert result['checks'][check] == dict(status='UNKNOWN', evidence=None)
    assert result['evidence'][phase] is None
    # Observation may refresh the other phase, but must preserve the old proof
    # that could not be revalidated and must not produce replacement work.
    assert state.journal.last['evidence'][phase] == historical[phase]
    assert restored.status()['historical'] is True and restored.status()['checks'][check]['status'] == 'PASS'
    assert restored.status()['evidence'][phase] == historical[phase]
    assert result['request_ids'] == original_ids and creates(state) == previous_creates


@pytest.mark.parametrize('side', ['local', 'server'])
def test_clock_regression_prevents_replay(state, side):
    review = state.flow.review_exchange('peer', BINDING)
    state.mcp.fault = 'before'
    with pytest.raises(ConnectionError):
        state.flow.send_exchange(review['review_revision'])
    setattr(state.clock, side, getattr(state.clock, side) - timedelta(seconds=1))
    with pytest.raises(ConnectionError) as error:
        state.reopen().send_exchange(review['review_revision'])
    assert error.value.code == 'REQUEST_CLOCK_CHANGED' and len(creates(state)) == 1


def test_revoked_message_observation_refuses_a_new_handoff(state):
    review = handoff_review(state)
    state.mcp.status_failure = ConnectionError('PERMISSION_DENIED', 'Synthetic revocation')
    with pytest.raises(ConnectionError) as error:
        state.reopen().send_handoff(review['review_revision'])
    assert error.value.code == 'PERMISSION_DENIED' and len(creates(state)) == 1


@pytest.mark.parametrize('timeout', [True, -1, float('inf'), float('nan'), 86401])
def test_invalid_deadline_is_refused_before_network(state, timeout):
    state.flow.review_exchange('peer', BINDING)
    with pytest.raises(ConnectionError) as error:
        state.flow.observe(timeout=timeout)
    assert error.value.code == 'OBSERVATION_TIMEOUT_INVALID' and state.mcp.calls == []


@pytest.mark.parametrize('change', [
    lambda d: d.update(scope=dict(SCOPE, agent_id='other')),
    lambda d: d.update(test_revision=True),
    lambda d: d.update(secret=SECRET),
    lambda d: d['consents'].update(exchange='wrong'),
    lambda d: d['request_ids'].update(message_create='replacement'),
    lambda d: d.update(peer='another'),
])
def test_invalid_saved_state_is_rejected_without_network(state, change):
    state.flow.review_exchange('peer', BINDING)
    change(state.journal.saved[-1])
    with pytest.raises(ConnectionError) as error:
        state.reopen()
    assert error.value.code == 'CHECKPOINT_INVALID' and state.mcp.calls == []


@pytest.mark.parametrize('phase', ['exchange', 'handoff'])
@pytest.mark.parametrize('resource_id', [None, '', 4, 'retained-resource'])
def test_pending_receipt_cannot_carry_historical_evidence_even_with_matching_ids(state, phase, resource_id):
    send_handoff(state)
    state.mcp.complete()
    state.flow.observe(timeout=0)
    saved = state.journal.saved[-1]
    saved['receipts'][phase].update(state='pending_approval', resource_id=resource_id, approval_id='approval-1')
    saved['evidence'][phase]['message_id' if phase == 'exchange' else 'handoff_id'] = resource_id
    # Keep the deterministic handoff review consistent so rejection specifically
    # concerns impossible evidence, rather than an unrelated digest mismatch.
    if phase == 'exchange':
        changed = deepcopy(state.flow.document)
        state.flow.document = deepcopy(saved)
        saved['reviews']['handoff'] = state.flow._digest('handoff')
        saved['consents']['handoff'] = saved['reviews']['handoff']
        state.flow.document = changed
    calls = deepcopy(state.mcp.calls)
    with pytest.raises(ConnectionError) as error:
        state.reopen()
    assert error.value.code == 'CHECKPOINT_INVALID' and state.mcp.calls == calls


@pytest.mark.parametrize('phase', ['exchange', 'handoff'])
@pytest.mark.parametrize('receipt_state', ['resource_removed', 'expired'])
def test_historical_evidence_preserves_valid_ids_after_resource_or_receipt_expiry(state, phase, receipt_state):
    send_handoff(state)
    state.mcp.complete()
    state.flow.observe(timeout=0)
    state.journal.saved[-1]['receipts'][phase]['state'] = receipt_state
    result = state.reopen().status()
    assert result['historical'] is True and all(check['status'] == 'PASS' for check in result['checks'].values())
