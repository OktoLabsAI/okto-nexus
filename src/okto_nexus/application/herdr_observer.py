"""Explicit Herdr binding and a durable, publish-only observation cycle.

The caller supplies read-only source/OS ports, a locked local journal and the
scoped HTTP publisher. Neither this flow nor its credential controls Herdr or
canonical Nexus work. A saved outbox always precedes publication.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re

from ..domain.herdr_observations import (
    HerdrObservationError, binding_from_dict, binding_to_dict, bind_agent,
    observation_from_dict, preview_hash, reconcile_binding,
)
from ..domain.observations import MAX_SEQUENCE, parse_report
from ..observation_client import ObservationClientError, normalize_server_origin


_FIELDS = frozenset({'document_version', 'herdr_executable', 'binding', 'server_origin',
    'source_id', 'observed_instance_id', 'generation', 'interval_seconds', 'valid_for_seconds',
    'sequence', 'checkpoint', 'pending', 'pending_failure', 'last_receipt', 'invalidated'})
_REFERENCE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z')


class ObserverError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__('Observation stopped: ' + code)


class ObserverPersistenceError(ObserverError):
    """HTTP may have completed, while its local outcome could not be saved."""

    def __init__(self, *, outcome_unknown, remote_admitted, receipt=None):
        self.outcome_unknown = outcome_unknown
        self.remote_admitted = remote_admitted
        self.receipt = receipt
        super().__init__('OBSERVER_OUTBOX_UNRESOLVED')


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _agent(snapshot, pane):
    matches = [agent for agent in snapshot['agents'] if agent['pane_id'] == pane]
    if len(matches) != 1:
        raise HerdrObservationError('HERDR_BOUND_OCCUPANT_MISSING')
    return matches[0]


def _selected_pid(info):
    processes = info['foreground_processes']
    if (len(processes) != 1 or info['shell_pid'] is None
            or processes[0]['pid'] == info['shell_pid']
            or processes[0]['pid'] != info['foreground_process_group_id']):
        raise HerdrObservationError('HERDR_OCCUPANT_UNPROVEN')
    return processes[0]['pid']


def sample_source(source, open_identity, *, pane, namespace=None, session=None,
                  binding=None, previous=None, clock=utc_now):
    """Bracket metadata with a held OS process handle and matching PID facts.

    The source's snapshots and PID facts are already strictly normalized. No
    timestamp from a cached/persisted snapshot is promoted to current time.
    """
    source.status()
    before = source.process_info(pane)
    with open_identity(_selected_pid(before)) as guard:
        guard.require_alive()
        snapshot = source.snapshot()
        observed_at = clock()
        agent = _agent(snapshot, pane)
        after = source.process_info(pane)
        if before != after:
            raise HerdrObservationError('HERDR_IDENTITY_CHANGED_DURING_READ')
        identity = guard.require_alive()
        if binding is None:
            binding = bind_agent(namespace=namespace, session=session, agent=agent,
                process_info=after, identity=identity, approved_image=identity.image_path)
        observation = reconcile_binding(binding, agent=agent, process_info=after,
                                         identity=identity, previous=previous)
        guard.require_alive()
    return binding, observation, observed_at


def selection_hash(document):
    """Consent covers the selected occupant AND the exact Nexus destination."""
    immutable = {key: document[key] for key in ('herdr_executable', 'binding', 'server_origin',
        'source_id', 'observed_instance_id', 'generation', 'interval_seconds', 'valid_for_seconds')}
    return 'sha256:' + hashlib.sha256(json.dumps(immutable, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def new_document(*, executable, binding, observation, server_origin, source_id,
                 observed_instance_id, generation, interval_seconds=15, valid_for_seconds=90):
    value = dict(document_version=1, herdr_executable=str(executable), binding=binding_to_dict(binding),
        server_origin=normalize_server_origin(server_origin), source_id=source_id,
        observed_instance_id=observed_instance_id, generation=generation,
        interval_seconds=interval_seconds, valid_for_seconds=valid_for_seconds, sequence=0,
        checkpoint=observation.to_dict(), pending=None, pending_failure=None,
        last_receipt=None, invalidated=False)
    return validate_document(value)


def validate_document(value):
    """Reject malformed local state. There is no reset or migration fallback."""
    try:
        if (type(value) is not dict or set(value) != _FIELDS
                or type(value['document_version']) is not int or value['document_version'] != 1
                or type(value['invalidated']) is not bool
                or not _integer(value['generation'], 1, MAX_SEQUENCE)
                or not _integer(value['sequence'], 0, MAX_SEQUENCE)
                or not _integer(value['interval_seconds'], 5, 300)
                or not _integer(value['valid_for_seconds'], 30, 3600)
                or value['valid_for_seconds'] < 2 * value['interval_seconds']
                or type(value['herdr_executable']) is not str
                or not re.match(r'^[A-Za-z]:[\\/]', value['herdr_executable'])
                or not value['herdr_executable'].isprintable()
                or normalize_server_origin(value['server_origin']) != value['server_origin']):
            raise ValueError
        for key in ('source_id', 'observed_instance_id'):
            if type(value[key]) is not str or not _REFERENCE.fullmatch(value[key]):
                raise ValueError
        binding = binding_from_dict(value['binding'])
        checkpoint = observation_from_dict(value['checkpoint'])
        if checkpoint.binding_hash != preview_hash(binding):
            raise ValueError
        pending = value['pending']
        if pending is not None:
            report = parse_report(pending)
            if (report.to_dict() != pending or value['sequence'] < 1
                    or any(getattr(report, key) != value[key] for key in
                           ('source_id', 'observed_instance_id', 'generation', 'sequence', 'valid_for_seconds'))):
                raise ValueError
        failure = value['pending_failure']
        if failure is not None and (pending is None or type(failure) is not dict
                or set(failure) != {'code', 'outcome_unknown'}
                or type(failure['outcome_unknown']) is not bool
                or type(failure['code']) is not str or not re.fullmatch(r'[A-Z_]{1,80}', failure['code'])):
            raise ValueError
        receipt = value['last_receipt']
        if receipt is not None:
            if (type(receipt) is not dict or set(receipt) != {'observed_instance_id', 'generation',
                    'sequence', 'report_hash', 'received_at', 'valid_until', 'replayed'}
                    or receipt['observed_instance_id'] != value['observed_instance_id']
                    or type(receipt['generation']) is not int or receipt['generation'] != value['generation']
                    or not _integer(receipt['sequence'], 1, value['sequence'])
                    or type(receipt['replayed']) is not bool
                    or type(receipt['report_hash']) is not str
                    or not re.fullmatch(r'sha256:[0-9a-f]{64}', receipt['report_hash'])):
                raise ValueError
            for key in ('received_at', 'valid_until'):
                stamp = receipt[key]
                if type(stamp) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z', stamp):
                    raise ValueError
                datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        return value
    except (KeyError, TypeError, ValueError, OverflowError, HerdrObservationError, ObservationClientError):
        raise ObserverError('OBSERVER_STATE_INVALID') from None
    except Exception:
        # Domain observation parsing also uses the Nexus application error type;
        # never display local document values through its validation detail.
        raise ObserverError('OBSERVER_STATE_INVALID') from None


class HerdrObserver:
    def __init__(self, *, source, open_identity, journal, publisher, clock=utc_now):
        self.source, self.open_identity = source, open_identity
        self.journal, self.publisher, self.clock = journal, publisher, clock

    def load(self):
        document = self.journal.read()
        if document is None:
            raise ObserverError('OBSERVER_BINDING_REQUIRED')
        return validate_document(document)

    def _publish_pending(self, document, *, recovery=False):
        previous_failure = document['pending_failure']
        # A loaded outbox without a result may be a crash after remote commit.
        # A refusal of THIS attempt cannot disprove a prior uncertain admission.
        prior_unknown = recovery and (previous_failure is None or previous_failure['outcome_unknown'])
        if recovery:
            # Reserve this new attempt durably too. Otherwise a crash after an
            # accepted retry would leave an older, known-refused result on disk.
            document['pending_failure'] = None
            self.journal.write(document)
        try:
            receipt = self.publisher.publish(document['pending'])['receipts'][0]
        except ObservationClientError as error:
            unknown = bool(prior_unknown or error.outcome_unknown)
            document['pending_failure'] = dict(code=error.code, outcome_unknown=unknown)
            try:
                self.journal.write(document)
            except Exception:
                raise ObserverPersistenceError(outcome_unknown=unknown,
                    remote_admitted=None if unknown else False) from None
            raise ObservationClientError(error.code, 'The saved report remains pending.',
                status=error.status, outcome_unknown=unknown,
                retry_after_seconds=error.retry_after_seconds) from None
        document.update(pending=None, pending_failure=None, last_receipt=receipt)
        try:
            self.journal.write(document)
        except Exception:
            raise ObserverPersistenceError(outcome_unknown=False, remote_admitted=True, receipt=receipt) from None
        return receipt

    def resolve_pending(self, *, retry=False, discard_refused=False):
        document = self.load()
        if retry and discard_refused:
            raise ObserverError('OBSERVER_RECOVERY_CHOICE_INVALID')
        if document['pending'] is None:
            if retry or discard_refused:
                raise ObserverError('OBSERVER_NO_PENDING_REPORT')
            return None
        if discard_refused:
            failure = document['pending_failure']
            if failure is None or failure['outcome_unknown'] is not False:
                raise ObserverError('OBSERVER_PENDING_OUTCOME_UNKNOWN')
            # Preserve the reserved sequence and checkpoint. Never recycle an
            # old number, even when a refusal proves that it was not admitted.
            document.update(pending=None, pending_failure=None)
            self.journal.write(document)
            return None
        if not retry:
            raise ObserverError('OBSERVER_PENDING_REPORT')
        # Explicit retry is the original historical report, not a fresh source
        # sample. It cannot renew validity or acquire a new generation.
        return self._publish_pending(document, recovery=True)

    def publish_current(self):
        document = self.load()
        if document['invalidated']:
            raise ObserverError('OBSERVER_REASSOCIATION_REQUIRED')
        if document['pending'] is not None:
            raise ObserverError('OBSERVER_PENDING_REPORT')
        if document['sequence'] == MAX_SEQUENCE:
            raise ObserverError('OBSERVER_SEQUENCE_EXHAUSTED')
        binding = binding_from_dict(document['binding'])
        previous = observation_from_dict(document['checkpoint'])
        try:
            _, observation, observed_at = sample_source(self.source, self.open_identity,
                pane=binding.pane_id, binding=binding, previous=previous, clock=self.clock)
        except HerdrObservationError as error:
            # An identity/contract contradiction is permanent for this binding;
            # transport unavailability is a separate exception and may recover.
            if getattr(error, 'requires_reassociation', True):
                document['invalidated'] = True
                self.journal.write(document)
            raise
        reason = {'working': 'external_activity', 'idle': 'external_idle',
                  'blocked': 'external_input_required', 'unknown': 'unknown'}[observation.state]
        report = dict(schema_version=1, source_id=document['source_id'],
            observed_instance_id=document['observed_instance_id'], generation=document['generation'],
            sequence=document['sequence'] + 1, state=observation.state, evidence=observation.evidence,
            observed_at=observed_at, valid_for_seconds=document['valid_for_seconds'], reason_code=reason)
        if observation.completion_ref is not None:
            report.update(current_completion_ref=observation.completion_ref, reason_code='external_completion')
        report = parse_report(report).to_dict()
        document.update(sequence=report['sequence'], checkpoint=observation.to_dict(),
                        pending=report, pending_failure=None)
        self.journal.write(document)
        return self._publish_pending(document)
