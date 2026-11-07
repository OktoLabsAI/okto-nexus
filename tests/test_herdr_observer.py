"""Deterministic flow tests; source/HTTP ports here are explicitly synthetic."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from okto_nexus.application.herdr_observer import (
    HerdrObserver, ObserverError, ObserverPersistenceError, new_document, sample_source, selection_hash, validate_document,
)
from okto_nexus.domain.herdr_observations import (
    HerdrObservationError, WindowsProcessIdentity, bind_agent, reconcile_binding,
)
from okto_nexus.domain.observations import MAX_SEQUENCE, parse_report, report_hash
from okto_nexus.observation_client import ObservationClientError


NOW = '2026-11-07T01:00:00.000000Z'
LATER = '2026-11-07T01:00:15.000000Z'
IDENTITY = WindowsProcessIdentity('a' * 64, 101, 134384870609652051, r'C:\fixture\agent.exe')


class Source:
    def __init__(self):
        self.agent = dict(workspace_id='w1', tab_id='w1:t1', pane_id='w1:p1', terminal_id='term_test',
            agent_status='working', revision=1, state_change_seq=1, completion_seq=None, agent_session=None)
        self.info = dict(pane_id='w1:p1', shell_pid=100, foreground_process_group_id=101,
                         foreground_processes=[dict(pid=101)])
        self.calls = []
        self.on_snapshot = None
        self.failure = None

    def status(self):
        self.calls.append('status')
        if self.failure is not None:
            raise self.failure

    def process_info(self, pane):
        self.calls.append(('process_info', pane))
        return deepcopy(self.info)

    def snapshot(self):
        self.calls.append('snapshot')
        if self.on_snapshot:
            self.on_snapshot()
        return dict(agents=[deepcopy(self.agent)])


class IdentityPort:
    def __init__(self):
        self.identity = IDENTITY
        self.checks = 0
        self.closed = 0
        self.fail_on_check = None

    @contextmanager
    def __call__(self, pid):
        assert pid == self.identity.pid
        try:
            yield self
        finally:
            self.closed += 1

    def require_alive(self):
        self.checks += 1
        if self.checks == self.fail_on_check:
            raise HerdrObservationError('HERDR_PROCESS_UNAVAILABLE')
        return self.identity


class Journal:
    def __init__(self, document):
        self.value = deepcopy(document)
        self.writes = []
        self.fail_on_write = None

    def read(self):
        return deepcopy(self.value)

    def write(self, document):
        self.writes.append(deepcopy(document))
        if len(self.writes) == self.fail_on_write:
            raise OSError('injected write failure')
        self.value = deepcopy(document)


class Publisher:
    def __init__(self, journal):
        self.journal, self.calls, self.failure = journal, [], None

    def publish(self, payload):
        # The complete intent is durable before every HTTP call, including retry.
        assert self.journal.value['pending'] == payload
        self.calls.append(deepcopy(payload))
        if self.failure is not None:
            raise self.failure
        report = parse_report(payload)
        until = datetime.fromisoformat(report.observed_at.replace('Z', '+00:00')) + timedelta(seconds=report.valid_for_seconds)
        return {'receipts': [dict(observed_instance_id=report.observed_instance_id, generation=report.generation,
            sequence=report.sequence, report_hash=report_hash(report), received_at=report.observed_at,
            valid_until=until.isoformat(timespec='microseconds').replace('+00:00', 'Z'), replayed=len(self.calls) > 1)]}


@pytest.fixture
def flow():
    source, identity = Source(), IdentityPort()
    binding = bind_agent(namespace='test-installation', session='test-session', agent=source.agent,
        process_info=source.info, identity=IDENTITY, approved_image=IDENTITY.image_path)
    baseline = reconcile_binding(binding, agent=source.agent, process_info=source.info, identity=IDENTITY)
    document = new_document(executable=r'C:\fixture\herdr.exe', binding=binding, observation=baseline,
        server_origin='http://127.0.0.1:8765', source_id='source-test', observed_instance_id='instance-test', generation=7)
    journal = Journal(document)
    publisher = Publisher(journal)
    observer = HerdrObserver(source=source, open_identity=identity, journal=journal, publisher=publisher, clock=lambda: NOW)
    return observer, source, identity, journal, publisher


def test_one_cycle_persists_intent_then_receipt_and_only_safe_metadata(flow):
    observer, source, identity, journal, publisher = flow
    receipt = observer.publish_current()
    assert receipt['sequence'] == 1 and receipt['generation'] == 7
    assert source.calls == ['status', ('process_info', 'w1:p1'), 'snapshot', ('process_info', 'w1:p1')]
    assert identity.checks == 3 and identity.closed == 1
    assert journal.writes[0]['pending'] == publisher.calls[0]
    assert journal.value['pending'] is None and journal.value['sequence'] == 1
    assert publisher.calls[0]['state'] == 'working' and publisher.calls[0]['evidence'] == 'inferred'
    assert not {'pid', 'image_path', 'agent_session', 'reason_text', 'binding'} & publisher.calls[0].keys()


def test_each_new_report_requires_new_snapshot_and_clock(flow):
    observer, source, _, journal, publisher = flow
    observer.publish_current()
    observer.clock = lambda: LATER
    observer.publish_current()
    assert [report['sequence'] for report in publisher.calls] == [1, 2]
    assert [report['observed_at'] for report in publisher.calls] == [NOW, LATER]
    assert source.calls.count('snapshot') == 2
    assert journal.value['last_receipt']['sequence'] == 2


def test_lost_response_stops_then_explicit_retry_uses_exact_historical_payload(flow):
    observer, source, _, journal, publisher = flow
    publisher.failure = ObservationClientError('TRANSPORT_ERROR', 'lost', outcome_unknown=True)
    with pytest.raises(ObservationClientError):
        observer.publish_current()
    original = deepcopy(journal.value['pending'])
    calls = list(source.calls)
    with pytest.raises(ObserverError, match='OBSERVER_PENDING_REPORT'):
        observer.publish_current()
    with pytest.raises(ObserverError, match='OBSERVER_PENDING_REPORT'):
        observer.resolve_pending()
    with pytest.raises(ObserverError, match='OBSERVER_PENDING_OUTCOME_UNKNOWN'):
        observer.resolve_pending(discard_refused=True)
    assert len(publisher.calls) == 1
    publisher.failure = None
    observer.clock = lambda: LATER
    observer.resolve_pending(retry=True)
    assert source.calls == calls and publisher.calls == [original, original]
    assert journal.value['sequence'] == 1 and journal.value['pending'] is None
    observer.publish_current()
    assert publisher.calls[-1]['observed_at'] == LATER and publisher.calls[-1]['sequence'] == 2


def test_known_refusal_can_be_discarded_without_reusing_sequence(flow):
    observer, _, _, journal, publisher = flow
    publisher.failure = ObservationClientError('VALIDATION_ERROR', 'expired', status=422)
    with pytest.raises(ObservationClientError):
        observer.publish_current()
    observer.resolve_pending(discard_refused=True)
    assert journal.value['sequence'] == 1 and journal.value['pending'] is None
    publisher.failure = None
    observer.clock = lambda: LATER
    observer.publish_current()
    assert publisher.calls[-1]['sequence'] == 2


@pytest.mark.parametrize('write_number,expected_calls', [(1, 0), (2, 1)])
def test_storage_failure_cannot_publish_without_intent_or_lose_pending(flow, write_number, expected_calls):
    observer, _, _, journal, publisher = flow
    journal.fail_on_write = write_number
    with pytest.raises(OSError if write_number == 1 else ObserverPersistenceError) as caught:
        observer.publish_current()
    assert len(publisher.calls) == expected_calls
    if write_number == 2:
        assert caught.value.remote_admitted is True and caught.value.outcome_unknown is False
        assert caught.value.receipt['sequence'] == 1
        assert journal.value['pending'] == publisher.calls[0]
        assert journal.value['pending_failure'] is None
        journal.fail_on_write = None
        observer.resolve_pending(retry=True)
        assert publisher.calls[0] == publisher.calls[1]


@pytest.mark.parametrize('prior_result', ['timeout', 'crash_before_receipt'])
def test_later_refusal_cannot_disprove_an_earlier_uncertain_admission(flow, prior_result):
    observer, _, _, journal, publisher = flow
    if prior_result == 'timeout':
        publisher.failure = ObservationClientError('TRANSPORT_ERROR', 'lost', outcome_unknown=True)
        with pytest.raises(ObservationClientError):
            observer.publish_current()
    else:
        journal.fail_on_write = 2
        with pytest.raises(ObserverPersistenceError):
            observer.publish_current()
        journal.fail_on_write = None
        assert journal.value['pending_failure'] is None
    original = deepcopy(journal.value['pending'])
    publisher.failure = ObservationClientError('AUTH_FAILED', 'refused', status=401)
    with pytest.raises(ObservationClientError) as caught:
        observer.resolve_pending(retry=True)
    assert caught.value.outcome_unknown is True and caught.value.status == 401
    assert journal.value['pending_failure']['outcome_unknown'] is True
    with pytest.raises(ObserverError, match='OBSERVER_PENDING_OUTCOME_UNKNOWN'):
        observer.resolve_pending(discard_refused=True)
    assert journal.value['pending'] == original
    publisher.failure = None
    observer.resolve_pending(retry=True)
    assert journal.value['pending'] is None


@pytest.mark.parametrize('unknown', [True, False])
def test_failure_to_persist_http_failure_keeps_uncertainty_visible(flow, unknown):
    observer, _, _, journal, publisher = flow
    publisher.failure = ObservationClientError('HTTP_ERROR', 'unavailable', outcome_unknown=unknown)
    journal.fail_on_write = 2
    with pytest.raises(ObserverPersistenceError) as caught:
        observer.publish_current()
    assert caught.value.outcome_unknown is unknown
    assert caught.value.remote_admitted is (None if unknown else False)
    assert caught.value.receipt is None
    assert journal.value['pending'] is not None and journal.value['pending_failure'] is None


def test_crash_during_retry_cannot_retain_a_previous_known_refusal(flow):
    observer, _, _, journal, publisher = flow
    publisher.failure = ObservationClientError('AUTH_FAILED', 'refused', status=401)
    with pytest.raises(ObservationClientError):
        observer.publish_current()
    assert journal.value['pending_failure']['outcome_unknown'] is False
    publisher.failure = None
    journal.fail_on_write = len(journal.writes) + 2  # attempt reservation succeeds; receipt save fails
    with pytest.raises(ObserverPersistenceError):
        observer.resolve_pending(retry=True)
    assert journal.value['pending_failure'] is None
    journal.fail_on_write = None
    publisher.failure = ObservationClientError('AUTH_FAILED', 'refused', status=401)
    with pytest.raises(ObservationClientError) as caught:
        observer.resolve_pending(retry=True)
    assert caught.value.outcome_unknown is True
    with pytest.raises(ObserverError, match='OBSERVER_PENDING_OUTCOME_UNKNOWN'):
        observer.resolve_pending(discard_refused=True)


@pytest.mark.parametrize('change', ['birth', 'image', 'host', 'pane_move', 'terminal', 'session', 'counter', 'missing'])
def test_identity_change_permanently_invalidates_without_publication(flow, change):
    observer, source, identity, journal, publisher = flow
    if change in {'birth', 'image', 'host'}:
        identity.identity = WindowsProcessIdentity('b' * 64 if change == 'host' else IDENTITY.host_id,
            IDENTITY.pid, IDENTITY.creation_filetime + (change == 'birth'),
            r'C:\fixture\other.exe' if change == 'image' else IDENTITY.image_path)
    elif change == 'pane_move':
        source.agent['tab_id'] = 'w1:t2'
    elif change == 'terminal':
        source.agent['terminal_id'] = 'term_replacement'
    elif change == 'session':
        source.agent['agent_session'] = dict(source='fixture', agent='fixture', kind='id', value='other')
    elif change == 'counter':
        source.agent['state_change_seq'] = 0
    else:
        source.agent['pane_id'] = 'w1:p2'
    with pytest.raises(HerdrObservationError):
        observer.publish_current()
    assert journal.value['invalidated'] is True and not publisher.calls
    with pytest.raises(ObserverError, match='OBSERVER_REASSOCIATION_REQUIRED'):
        observer.publish_current()


def test_process_switch_between_reads_and_process_exit_are_not_published(flow):
    observer, source, _, journal, publisher = flow
    source.on_snapshot = lambda: source.info.update(shell_pid=999)
    with pytest.raises(HerdrObservationError, match='HERDR_IDENTITY_CHANGED_DURING_READ'):
        observer.publish_current()
    assert journal.value['invalidated'] and not publisher.calls


@pytest.mark.parametrize('check', [1, 2, 3])
def test_held_process_handle_checked_across_snapshot(flow, check):
    observer, _, identity, journal, publisher = flow
    identity.fail_on_check = check
    with pytest.raises(HerdrObservationError):
        observer.publish_current()
    assert identity.closed == 1 and journal.value['invalidated'] and not publisher.calls


def test_disconnect_recovers_only_with_new_live_snapshot(flow):
    observer, source, _, journal, publisher = flow
    class Unavailable(HerdrObservationError):
        requires_reassociation = False
    source.failure = Unavailable('HERDR_SERVER_UNAVAILABLE')
    with pytest.raises(HerdrObservationError):
        observer.publish_current()
    assert not journal.value['invalidated'] and not publisher.calls
    assert source.calls == ['status']
    source.failure = None
    observer.clock = lambda: LATER
    observer.publish_current()
    assert publisher.calls[0]['observed_at'] == LATER


def test_real_transport_alias_target_change_requires_persistent_reassociation(flow):
    from okto_nexus.adapters.outbound.observation.herdr import HerdrTransportError
    observer, source, _, journal, publisher = flow
    source.failure = HerdrTransportError('HERDR_TARGET_CHANGED')
    with pytest.raises(HerdrObservationError, match='HERDR_TARGET_CHANGED'):
        observer.publish_current()
    assert journal.value['invalidated'] is True and not publisher.calls
    # Restoring a transport response cannot silently restore a moved binding.
    source.failure = None
    with pytest.raises(ObserverError, match='OBSERVER_REASSOCIATION_REQUIRED'):
        observer.publish_current()


def test_new_completion_is_stable_observation_never_a_business_command(flow):
    observer, source, _, journal, publisher = flow
    source.agent.update(agent_status='done', revision=2, state_change_seq=2, completion_seq=2)
    observer.publish_current()
    observer.clock = lambda: LATER
    observer.publish_current()
    first, second = publisher.calls
    assert first['state'] == second['state'] == 'idle'
    assert first['current_completion_ref'] == second['current_completion_ref']
    assert first['reason_code'] == second['reason_code'] == 'external_completion'
    assert journal.value['checkpoint']['last_completion_seq'] == 2


def test_initial_done_only_sets_baseline(flow):
    _, source, identity, _, _ = flow
    source.agent.update(agent_status='done', state_change_seq=5, completion_seq=5)
    _, observation, stamp = sample_source(source, identity, pane='w1:p1', namespace='other', session='session', clock=lambda: NOW)
    assert observation.state == 'idle' and observation.completion_ref is None and stamp == NOW


def test_selection_covers_destination_generation_and_process_not_activity(flow):
    _, _, _, journal, _ = flow
    document = journal.read()
    original = selection_hash(document)
    for key, value in [('source_id', 'other'), ('observed_instance_id', 'other'), ('generation', 8),
                       ('server_origin', 'https://other.example'), ('valid_for_seconds', 120)]:
        changed = deepcopy(document)
        changed[key] = value
        assert selection_hash(changed) != original
    document['checkpoint']['revision'] += 1
    assert selection_hash(document) == original


@pytest.mark.parametrize('key,value', [('generation', True), ('sequence', -1), ('interval_seconds', 0),
    ('valid_for_seconds', 1), ('invalidated', 0), ('document_version', True), ('checkpoint', {}),
    ('server_origin', 'http://remote.example'), ('source_id', 'bad id'), ('extra', 'unexpected')])
def test_malformed_journal_never_resets_or_publishes(flow, key, value):
    observer, _, _, journal, publisher = flow
    journal.value[key] = value
    before = deepcopy(journal.value)
    with pytest.raises(ObserverError, match='OBSERVER_STATE_INVALID'):
        observer.publish_current()
    assert journal.value == before and not journal.writes and not publisher.calls


def test_sequence_exhaustion_never_wraps(flow):
    observer, source, _, journal, publisher = flow
    journal.value['sequence'] = MAX_SEQUENCE
    with pytest.raises(ObserverError, match='OBSERVER_SEQUENCE_EXHAUSTED'):
        observer.publish_current()
    assert not source.calls and not publisher.calls


def test_refused_or_uncertain_recovery_requires_a_pending_report(flow):
    observer, _, _, journal, publisher = flow
    for choice in ({'retry': True}, {'discard_refused': True}):
        with pytest.raises(ObserverError, match='OBSERVER_NO_PENDING_REPORT'):
            observer.resolve_pending(**choice)
    assert observer.resolve_pending() is None
    assert validate_document(journal.read()) == journal.value and not publisher.calls
