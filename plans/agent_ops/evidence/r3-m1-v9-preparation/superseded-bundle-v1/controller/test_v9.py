"""Pure transport fixtures: no HTTP, native process, credential or service."""
from copy import deepcopy
import hashlib
import json

import pytest

from controller import ANCESTRY, POLICY, Controller, Refused, seal
import setup_journal
import token_collector as tokens
from canonical_fixture import event, page, scope


@pytest.fixture(autouse=True)
def deny_effects(monkeypatch):
    import socket
    import subprocess
    import win32cred

    def forbidden(*args, **kwargs):
        raise AssertionError('External effect forbidden in this preparation')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    for name in ('CredRead', 'CredWrite', 'CredDelete', 'CredEnumerate'):
        monkeypatch.setattr(win32cred, name, forbidden)


def approval(root, **changes):
    path = root / 'synthetic-approval.json'
    document = {'status': 'USER_APPROVED', 'proposal_revision': 9,
                'proposal_sha256': 'a' * 64,
                'policy': deepcopy(POLICY), 'ancestry': deepcopy(ANCESTRY),
                'user_quote': 'SYNTHETIC TEST FIXTURE ONLY', 'campaign_root': str(root.resolve())}
    document.update(changes)
    path.write_text(json.dumps(document), encoding='utf-8')
    return {'approval_path': path, 'approval_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'expected_proposal_sha256': 'a' * 64}


class Flow:
    def __init__(self):
        self.document = {}
        self.events = []
        self.productive = []
        self.new_sessions = []
        self.controls = []
        self.binding_reads = 0

    def binding(self):
        self.binding_reads += 1
        return scope()

    def submit(self, text=None, *, client_intent_id, new_session=False, **kwargs):
        if kwargs.get('action'):
            self.controls.append((kwargs['action'], client_intent_id))
            return {}
        self.productive.append(client_intent_id)
        self.new_sessions.append(new_session)
        self.document['session_id'] = scope()['session_id']
        return {'scope': scope(), 'operation_id': 'op-' + client_intent_id}

    def observe(self, *, session_id, after_sequence):
        assert session_id == scope()['session_id']
        return {'events': page(self.events[after_sequence:], after=after_sequence)}

    def emit(self, method, total=10):
        name = self.productive[-1]
        self.events.append(event(len(self.events) + 1, method, total=total,
                                 op='op-' + name, turn='turn-' + name))

    def complete(self, total=10):
        for method in ('turn/started', 'thread/tokenUsage/updated', 'turn/completed'):
            self.emit(method, total)


def owned(root, *, authorized=True, clock=None):
    auth = approval(root) if authorized else {}
    control = Controller(root / 'controller.json', root, create=True,
                         clock=clock or (lambda: 1000), **auth)
    flow = Flow()
    home = root / 'owner'
    home.mkdir()
    stops = []
    control.attach_owner('local', home, lambda: stops.append('owned-stop'))
    control.attach('local', flow)
    return control, flow, home, stops, auth


def test_default_is_unapproved_and_carries_history_before_any_dispatch(tmp_path):
    control, flow, home, stops, _ = owned(tmp_path, authorized=False)
    try:
        summary = control.poll()
        assert summary['known_observed_tokens'] == 45843 and summary['reserved_requests'] == 3
        assert summary['new_reserved_requests'] == 0 and summary['new_observed_tokens'] == 0
        assert summary['reasons'] == ['V9_APPROVAL_REQUIRED']
        with pytest.raises(Refused, match='APPROVAL_REQUIRED'):
            control.work('work', 'local', 'Must not dispatch')
        with pytest.raises(Refused, match='APPROVAL_REQUIRED'):
            control.setup('setup', 'local', home, lambda: pytest.fail('dispatch'), lambda: None)
        assert flow.productive == [] and flow.binding_reads == 0 and stops == []
        assert control.data['ancestry']['predecessor_faults'] == ['SETUP_CLI_RETURNED_WITHOUT_SETTLED_USAGE']
        assert control.data['ancestry']['prior_ancestry']['predecessor_faults'] == ['CAMPAIGN_RUNNER_EXCEPTION']
    finally:
        control.close()


def test_work_over_100k_but_cumulative_under_200k_remains_admissible(tmp_path):
    control, flow, _, _, _ = owned(tmp_path)
    try:
        control.work('one', 'local', 'synthetic')
        flow.complete(100001)
        result = control.poll()
        assert result['known_observed_tokens'] == 145844 and result['can_admit']
        control.work('two', 'local', 'synthetic', stage='continuation')
        assert flow.productive == ['one', 'two'] and not flow.controls
        assert flow.new_sessions == [True, False]
        assert control.accounting['max_requests'] == 6 and control.accounting['stop_at'] == 200000
    finally:
        control.close()


def test_carry_plus_setup_plus_work_selects_interrupt_at_cumulative_200k(tmp_path, monkeypatch):
    control, flow, home, stops, _ = owned(tmp_path)

    def read(record, *args):
        return record | dict(high_water=20000, started=True, terminal=True, usage_seen=True,
                             caught_up=True, result_stage='SUCCEEDED', close_stage='SUBMITTED',
                             owned_slot_released=True)
    monkeypatch.setattr(setup_journal, 'poll', read)
    try:
        dispatches = []
        control.setup('setup', 'local', home, lambda: dispatches.append(1), lambda: stops.append('owned-stop'))
        assert control.poll()['known_observed_tokens'] == 65843
        control.work('work', 'local', 'synthetic')
        flow.emit('turn/started')
        flow.emit('thread/tokenUsage/updated', 134157)
        result = control.poll()
        assert result['known_observed_tokens'] == 200000 and not result['can_admit']
        assert control.data['requests']['work']['stop_selected'] == {'reason': 'PREVENTIVE_THRESHOLD', 'action': 'interrupt'}
        assert flow.controls == [('interrupt', 'm1-stop-work')] and stops == [] and dispatches == [1]
        control.poll()
        assert len(flow.controls) == 1
        with pytest.raises(Refused):
            control.work('extra', 'local', 'forbidden')
        assert flow.productive == ['work']
    finally:
        control.close()


def test_six_new_admissions_are_nine_cumulative_and_seventh_never_dispatches(tmp_path):
    control, flow, _, _, _ = owned(tmp_path)
    try:
        for index in range(6):
            control.work('work-' + str(index), 'local', 'synthetic')
            flow.complete(10 + index)
            control.poll()
        summary = control.summary()
        assert summary['reserved_requests'] == 9 and summary['new_reserved_requests'] == 6
        assert 'GLOBAL_ALLOCATION_EXHAUSTED' in summary['reasons']
        with pytest.raises(Refused):
            control.work('seventh', 'local', 'forbidden')
        assert len(flow.productive) == 6
    finally:
        control.close()


def test_resume_preserves_carry_highwater_reservations_and_permanent_fault(tmp_path):
    control, flow, home, stops, auth = owned(tmp_path)
    control.work('one', 'local', 'synthetic')
    flow.complete(101000)
    control.poll()
    control.fault('SYNTHETIC_OBSERVATION_FAILURE')
    previous = control.summary()
    control.close()
    restored = Controller(tmp_path / 'controller.json', tmp_path, clock=lambda: 1000, **auth)
    try:
        restored.attach_owner('local', home, lambda: stops.append('owned-stop'))
        restored.attach('local', flow)
        assert restored.poll() == previous
        assert not restored.summary()['can_admit']
        with pytest.raises(Refused):
            restored.work('extra', 'local', 'forbidden')
        assert flow.productive == ['one']
        restored.data['faults'] = []
        with pytest.raises(Refused, match='REGRESSION'):
            restored.persist()
    finally:
        restored.close()


@pytest.mark.parametrize('change', ['carry', 'budget', 'max', 'ancestry', 'root', 'zeroed', 'legacy'])
def test_resume_refuses_zeroing_changed_policy_or_ancestry(tmp_path, change):
    control, flow, _, _, auth = owned(tmp_path)
    control.work('one', 'local', 'synthetic')
    flow.complete(5)
    control.poll()
    path = control.path
    control.close()
    state = json.loads(path.read_bytes())
    if change == 'carry': state['policy']['carry_in_tokens'] = 0
    elif change == 'budget': state['policy']['preventive_cumulative_tokens'] = 700000
    elif change == 'max': state['policy']['max_new_admissions'] = 7
    elif change == 'ancestry': state['ancestry']['checkpoint_sha256'] = '0' * 64
    elif change == 'root': state['root'] += '-other'
    elif change == 'legacy': state['format'] = 8
    else:
        state['collector'] = tokens.checkpoint(tokens.initial_state())
        state['requests'] = {}
    if change != 'zeroed': state['state_sha256'] = seal(state)
    path.write_text(json.dumps(state), encoding='utf-8')
    with pytest.raises(Refused, match='STATE_INVALID'):
        Controller(path, tmp_path, **auth)
    assert json.loads(path.read_text()) == state  # no repair or fresh fallback


def test_approval_file_change_blocks_dispatch_and_cannot_be_rebound(tmp_path):
    control, flow, _, _, auth = owned(tmp_path)
    auth['approval_path'].write_text('{}', encoding='utf-8')
    try:
        with pytest.raises(Refused, match='APPROVAL_REQUIRED'):
            control.work('one', 'local', 'forbidden')
        assert not flow.productive
    finally:
        control.close()
    new_auth = approval(tmp_path, user_quote='DIFFERENT SYNTHETIC APPROVAL')
    with pytest.raises(Refused, match='APPROVAL_CHANGED'):
        Controller(tmp_path / 'controller.json', tmp_path, **new_auth)


@pytest.mark.parametrize('expected', [None, 'b' * 64, 'invalid'])
def test_valid_approval_receipt_does_not_authorize_missing_or_different_proposal(tmp_path, expected):
    auth = approval(tmp_path)
    auth['expected_proposal_sha256'] = expected
    control = Controller(tmp_path / 'controller.json', tmp_path, create=True, **auth)
    try:
        assert not control.summary()['can_admit']
        assert control.data['authorization_sha256'] is None and control.data['proposal_sha256'] is None
        with pytest.raises(Refused, match='APPROVAL_REQUIRED'):
            control.work('work', 'local', 'no binding/dispatch')
    finally:
        control.close()


def test_resume_cannot_change_pinned_proposal_even_with_other_valid_receipt(tmp_path):
    control, _, _, _, _ = owned(tmp_path)
    control.close()
    auth = approval(tmp_path, proposal_sha256='b' * 64)
    auth['expected_proposal_sha256'] = 'b' * 64
    before = (tmp_path / 'controller.json').read_bytes()
    with pytest.raises(Refused, match='PROPOSAL_CHANGED'):
        Controller(tmp_path / 'controller.json', tmp_path, **auth)
    assert (tmp_path / 'controller.json').read_bytes() == before


def test_deadline120_stays_serial_and_selects_only_one_control(tmp_path):
    now = [1000]
    control, flow, _, _, _ = owned(tmp_path, clock=lambda: now[0])
    try:
        control.work('one', 'local', 'synthetic')
        flow.emit('turn/started')
        now[0] += 120
        control.poll()
        assert control.data['requests']['one']['stop_selected']['reason'] == 'DEADLINE120'
        control.poll()
        assert flow.controls == [('interrupt', 'm1-stop-one')]
        with pytest.raises(Refused): control.work('two', 'local', 'forbidden')
    finally:
        control.close()


def test_create_cannot_overwrite_checkpoint_and_legacy_collector_is_rejected(tmp_path):
    control, _, _, _, auth = owned(tmp_path)
    control.close()
    before = (tmp_path / 'controller.json').read_bytes()
    with pytest.raises(FileExistsError):
        Controller(tmp_path / 'controller.json', tmp_path, create=True, **auth)
    assert (tmp_path / 'controller.json').read_bytes() == before
    checkpoint = tokens.checkpoint(tokens.initial_state())
    checkpoint['format'] = 'm1-token-collector-v1'
    with pytest.raises(tokens.Invalid, match='CHECKPOINT_INVALID'):
        tokens.restore(checkpoint)


@pytest.mark.parametrize('case', ['foreign', 'scope_mismatch', 'ambiguous', 'retired'])
def test_existing_session_requires_one_owned_active_stream_before_reservation(tmp_path, case):
    from canonical_fixture import enroll_ready

    control, flow, _, _, _ = owned(tmp_path)
    flow.document['session_id'] = scope()['session_id']
    try:
        if case != 'foreign':
            selected = scope()
            if case == 'scope_mismatch':
                selected['binding_id'] = 'another-binding'
            state, stream = enroll_ready(selected=selected)
            if case == 'retired':
                state['streams'][stream]['retired'] = True
            elif case == 'ambiguous':
                state, _ = enroll_ready(state, selected=selected, epoch='other-epoch')
            control.persist(state)
        before = control.path.read_bytes()
        with pytest.raises(Refused, match='SESSION_NOT_OWNED_BY_CONTROLLER'):
            control.work('foreign-work', 'local', 'must not dispatch')
        assert flow.productive == [] and flow.controls == []
        assert control.data['requests'] == {} and control.accounting['requests'] == {}
        assert control.path.read_bytes() == before
        assert control.summary()['reserved_requests'] == 3
    finally:
        control.close()


def test_previous_v8_receipt_never_authorizes_v9_reservation(tmp_path):
    auth = approval(tmp_path, proposal_revision=8)
    control = Controller(tmp_path / 'controller.json', tmp_path, create=True, **auth)
    try:
        before = control.path.read_bytes()
        with pytest.raises(Refused, match='V9_APPROVAL_REQUIRED'):
            control.work('new', 'local', 'no dispatch')
        assert control.path.read_bytes() == before
        assert control.summary()['reserved_requests'] == 3
        assert control.data['requests'] == {}
    finally:
        control.close()
