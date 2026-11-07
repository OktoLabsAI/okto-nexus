"""Operator-selected native correlation; proof acquisition belongs to the host.

Preparation closes its read transaction before the host awaits Core or reads OS
identity. Commit reauthenticates and fences all facts in one short transaction.
The stored birth comparison is historical evidence, never execution authority.
"""
import json

from ..domain.observation_correlation import (
    MAX_INT64, ObservationCorrelationError, correlation_digest, normalize_evidence, normalize_selection,
)
from ..errors import ErrorCode, OktoNexusError
from . import observation_validation as check
from .observations import _stamp


def refused(reason='OBSERVATION_CORRELATION_CHANGED', code=ErrorCode.CONFLICT):
    raise OktoNexusError(code, 'The selected observation correlation is unavailable.', {'reason': reason})


def canonical_matches(row, selection, *, agent_id, workspace_id, live=False):
    """Compare exact current relationships; absence never means a fresh match."""
    if row is None:
        return False
    if any(row[name] != selection[name] for name in (
            'server_id', 'executor_id', 'session_id', 'open_operation_id',
            'binding_id', 'workspace_binding_id', 'stream_epoch')):
        return False
    if (row['owner_generation'] != selection['session_owner_generation']
            or row['opening_action'] != 'runtime.open'
            or row['opening_session_id'] != selection['session_id']
            or row['opening_binding_id'] != selection['binding_id']
            or any(row[name] != selection['workspace_binding_id'] for name in (
                'opening_workspace_binding_id', 'binding_workspace_binding_id', 'realization_workspace_binding_id'))
            or any(row[name] != agent_id for name in ('subject_agent_id', 'endpoint_agent_id', 'realization_agent_id'))
            or any(row[name] != workspace_id for name in (
                'workspace_id', 'opening_workspace_id', 'endpoint_workspace_id', 'bound_workspace_id'))):
        return False
    try:
        stored = json.loads(row['expected_revisions_json'])
    except (TypeError, ValueError):
        return False
    expected = {name: selection[name] for name in (
        'server_id', 'executor_id', 'session_id', 'binding_id', 'workspace_binding_id', 'session_owner_generation')}
    expected.update(binding_revision=row['binding_revision'], agent_id=agent_id, workspace_id=workspace_id)
    if (type(stored) is not dict or any(type(stored.get(name)) is not type(value)
            or stored[name] != value for name, value in expected.items())):
        return False
    if (row['kind'] != 'embedded' or row['revoked_at'] is not None
            or row['protocol'] != 'nxl-r4' or not row['endpoint_enabled']
            or row['activation_state'] != 'approved' or row['health'] == 'quarantined'
            or row['realization_revision'] != row['current_realization_revision']
            or row['realization_status'] != 'READY' or row['workspace_status'] != 'READY'):
        return False
    return not live or row['control_state'] == 'CONTROL_READY' and row['lifecycle_state'] == 'READY'


class ObservationCorrelationService:
    def __init__(self, *, observations, repository, facts):
        self.observations, self.repo, self.facts = observations, repository, facts
        self.factory, self.clock, self.config = observations.factory, observations.clock, observations.config

    def _operator(self, uow, context):
        operator, _ = self.observations._actor(uow, context)
        if not operator:
            refused('OBSERVATION_CORRELATION_OPERATOR_REQUIRED', ErrorCode.PERMISSION_DENIED)

    def _instance(self, uow, observed_instance_id):
        row = self.observations.repo.get_current(uow, observed_instance_id=observed_instance_id)
        if row is None:
            refused('OBSERVATION_INSTANCE_UNAVAILABLE', ErrorCode.NOT_FOUND)
        return row

    def _current(self, uow, selection, *, context, verify_owner):
        self._operator(uow, context)
        self.observations._feature()
        row = self._instance(uow, selection['observed_instance_id'])
        source, instance = row['source'], row['instance']
        if (source['source_id'] != selection['source_id'] or source['revision'] != selection['source_revision']
                or instance['generation'] != selection['generation']):
            refused()
        self.observations._source(uow, context, source['source_id'], operator_only=True, available=True)
        if instance['workspace_id'] not in source['allowed_workspace_ids']:
            refused()
        if self.observations._project(row, _stamp(self.clock.now_iso()), self.config)['freshness'] == 'unavailable':
            refused('OBSERVATION_SOURCE_UNAVAILABLE')
        native = self.facts.session(uow, **{name: selection[name] for name in ('server_id', 'executor_id', 'session_id')})
        if not canonical_matches(native, selection, agent_id=source['agent_id'],
                                 workspace_id=instance['workspace_id'], live=True):
            refused()
        verify_owner(uow=uow, selection=selection, native=native)
        stored = self.repo.get(uow, observed_instance_id=selection['observed_instance_id'])
        if (stored['revision'] if stored else 0) != selection['expected_correlation_revision']:
            refused('OBSERVATION_CORRELATION_REVISION_CHANGED')
        return row

    def prepare(self, *, context, observed_instance_id, body, verify_owner):
        check.identity(observed_instance_id, 'observed_instance_id')
        check.fields(body, ('selection', 'evidence'))
        try:
            selection, evidence = normalize_selection(body['selection']), normalize_evidence(body['evidence'])
        except ObservationCorrelationError:
            refused('OBSERVATION_CORRELATION_INVALID', ErrorCode.VALIDATION_ERROR)
        if selection['observed_instance_id'] != observed_instance_id:
            refused('OBSERVATION_CORRELATION_INVALID', ErrorCode.VALIDATION_ERROR)
        with self.factory.unit_of_work(write=False) as uow:
            row = self._current(uow, selection, context=context, verify_owner=verify_owner)
        return dict(selection=selection, evidence=evidence, agent_id=row['source']['agent_id'],
                    workspace_id=row['instance']['workspace_id'])

    def revalidate(self, *, context, prepared, verify_owner):
        """Reauthenticate after Core's await, before the next privileged read."""
        with self.factory.unit_of_work(write=False) as uow:
            row = self._current(uow, normalize_selection(prepared['selection']),
                context=context, verify_owner=verify_owner)
            if (row['source']['agent_id'] != prepared['agent_id']
                    or row['instance']['workspace_id'] != prepared['workspace_id']):
                refused()

    def commit(self, *, context, prepared, proof, verified_at, verify_owner, check_budget):
        selection = normalize_selection(prepared['selection'])
        # The HTTP body cannot supply this proof; only the host's comparison can.
        correlation_digest(selection, proof)
        with self.factory.unit_of_work() as uow:
            row = self._current(uow, selection, context=context, verify_owner=verify_owner)
            if (row['source']['agent_id'] != prepared['agent_id']
                    or row['instance']['workspace_id'] != prepared['workspace_id']):
                refused()
            check_budget()
            now = _stamp(self.clock.now_iso())
            self.observations._budget(uow, source_id=selection['source_id'], agent_id=prepared['agent_id'], cost=1, now=now)
            check_budget()
            value = self.repo.replace_selection(uow, selection=selection, proof=proof,
                verified_at=verified_at, now=now, max_records=self.config.observation_max_correlation_records,
                agent_id=prepared['agent_id'], workspace_id=prepared['workspace_id'])
            self._audit(uow, context, value)
            check_budget()
        return dict(correlation=self._public(value, current=True))

    def _audit(self, uow, context, value):
        self.observations.events.emit(uow, type='observation.correlation', stream='workspace',
            actor_agent_id=context.actor_agent_id, workspace_id=value['workspace_id'],
            visibility='private', target=json.dumps(dict(strategy='direct', agent_id='operator')),
            payload=dict(observed_instance_id=value['observed_instance_id'], revision=value['revision'],
                state=value['state'], digest=value['digest'], authenticated_via=context.authentication_source))

    @staticmethod
    def _public(value, *, current):
        if value is None:
            return dict(revision=0, state='absent', current=False, selection=None, digest=None,
                        provenance=None, verified_at=None, updated_at=None)
        return {key: value[key] for key in ('revision', 'state', 'selection', 'digest',
                'provenance', 'verified_at', 'updated_at')} | dict(current=current)

    def read(self, *, context, observed_instance_id):
        check.identity(observed_instance_id, 'observed_instance_id')
        with self.factory.unit_of_work(write=False) as uow:
            self._operator(uow, context)
            value = self.repo.get(uow, observed_instance_id=observed_instance_id)
            row = self.observations.repo.get_current(uow, observed_instance_id=observed_instance_id)
            if row is None and value is None:
                refused('OBSERVATION_INSTANCE_UNAVAILABLE', ErrorCode.NOT_FOUND)
            current = False
            if row is not None and value is not None and value['state'] == 'selected':
                selected = value['selection']
                native = self.facts.session(uow, **{name: selected[name] for name in ('server_id', 'executor_id', 'session_id')})
                view = self.observations._project(row, _stamp(self.clock.now_iso()), self.config)
                current = (view['freshness'] != 'unavailable'
                    and selected['source_id'] == row['source']['source_id']
                    and selected['source_revision'] == row['source']['revision']
                    and selected['generation'] == row['instance']['generation']
                    and value['agent_id'] == row['source']['agent_id']
                    and value['workspace_id'] == row['instance']['workspace_id']
                    and canonical_matches(native, selected, agent_id=value['agent_id'], workspace_id=value['workspace_id']))
        return dict(correlation=self._public(value, current=current))

    def clear(self, *, context, observed_instance_id, body):
        check.identity(observed_instance_id, 'observed_instance_id')
        check.fields(body, ('expected_revision',))
        revision = body['expected_revision']
        if type(revision) is not int or not 0 <= revision <= MAX_INT64:
            check.invalid('expected_revision')
        with self.factory.unit_of_work() as uow:
            self._operator(uow, context)
            existing = self.repo.get(uow, observed_instance_id=observed_instance_id)
            row = self.observations.repo.get_current(uow, observed_instance_id=observed_instance_id)
            if row is None and existing is None:
                refused('OBSERVATION_INSTANCE_UNAVAILABLE', ErrorCode.NOT_FOUND)
            agent_id = existing['agent_id'] if existing else row['source']['agent_id']
            workspace_id = existing['workspace_id'] if existing else row['instance']['workspace_id']
            now = _stamp(self.clock.now_iso())
            self.observations._budget(uow, source_id=row['source']['source_id'] if row else None,
                agent_id=agent_id, cost=1, now=now)
            value = self.repo.tombstone(uow, observed_instance_id=observed_instance_id,
                expected_revision=revision, state='cleared', now=now,
                max_records=self.config.observation_max_correlation_records, agent_id=agent_id, workspace_id=workspace_id)
            self._audit(uow, context, value)
        return dict(correlation=self._public(value, current=False))
