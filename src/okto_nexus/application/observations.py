"""Optional external activity, isolated from coordination and runtime admission.

The publish transaction authenticates current facts before considering replay.
Only auxiliary state, quotas and private observational events are written.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import time

from ..domain.observation_tokens import (
    generate_observation_token, hash_observation_token, is_well_formed_observation_token,
)
from ..domain.observations import ObservationLimits, compute_freshness, parse_report, report_hash
from ..domain.permissions import PermissionSet
from ..errors import ErrorCode, OktoNexusError
from . import observation_validation as check
from .observation_ingress import ObservationIngress
from .observation_correlation_ports import ObservationCorrelationProjection


def _time(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Observation timestamps require an explicit timezone.')
    return parsed.astimezone(timezone.utc)


def _stamp(value):
    return _time(value).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _denied():
    raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Observation access is not authorized.', {})


def _conflict():
    raise OktoNexusError(ErrorCode.CONFLICT, 'The observation binding changed. Refresh its registration.', {})


class ObservationService:
    def __init__(self, *, deps, access, correlations: ObservationCorrelationProjection | None = None):
        self.factory, self.config, self.clock = deps.connection_factory, deps.config, deps.clock
        self.repo, self.agents, self.workspaces = deps.repos.observations, deps.repos.agents, deps.repos.workspaces
        self.events, self.access = deps.event_emitter, access
        self.ingress = ObservationIngress(self.config)
        self.correlations = correlations

    def _feature(self):
        if not self.config.feature_observations:
            raise OktoNexusError('FEATURE_DISABLED', 'External observation ingestion is disabled.', {})

    def _actor(self, uow, context):
        if context is None:
            _denied()
        operator = self.access.authenticate(context, uow=uow, require_feature=False)
        if operator:
            return True, context.actor_agent_id
        actor = self.agents.get(uow, context.actor_agent_id)
        if actor is None or not PermissionSet(actor.permissions).allows('observations', 'manage_self'):
            _denied()
        return False, actor.agent_id

    def _source(self, uow, context, source_id, *, operator_only=False, available=False):
        check.identity(source_id, 'source_id')
        operator, actor_id = self._actor(uow, context)
        if operator_only and not operator:
            _denied()
        source = self.repo.get_source(uow, source_id=source_id)
        if source is None or not operator and source['agent_id'] != actor_id:
            # Do not reveal another actor's source or its revision.
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Observation source is unavailable.', {})
        if available:
            subject = self.agents.get(uow, source['agent_id'])
            if (not source['enabled'] or source['revoked_at'] or subject is None
                    or not subject.is_active or not subject.api_key_hash):
                _denied()
        return source

    def _budget(self, uow, *, source_id, agent_id, cost, now):
        rates = {name: (getattr(self.config, f'observation_{name}_rate_per_minute'),
                        getattr(self.config, f'observation_{name}_burst'))
                 for name in ('source', 'agent', 'installation')}
        result = self.repo.consume_budget(uow, source_id=source_id, agent_id=agent_id,
                                          cost=cost, now=now, rates=rates)
        if not result['allowed']:
            raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, 'The observation budget is exhausted.',
                {'retry_after_seconds': result['retry_after_seconds']}, retryable=True)

    def _workspaces(self, uow, values):
        ids = check.workspaces(values)
        if any(self.workspaces.get(uow, workspace_id) is None for workspace_id in ids):
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'An approved workspace is unavailable.', {})
        return ids

    @staticmethod
    def _page(after, limit):
        if after is not None:
            check.identity(after, 'after')
        check.number(limit, 'limit', maximum=200)

    def create_source(self, *, context, body):
        check.fields(body, ('agent_id', 'source_kind', 'workspace_ids', 'registration_ref'))
        agent_id = check.identity(body['agent_id'], 'agent_id')
        registration_ref = check.opaque(body['registration_ref'], 'registration_ref', 160)
        if body['source_kind'] not in ('herdr', 'hook', 'custom'):
            check.invalid('source_kind')
        with self.factory.unit_of_work() as uow:
            self._feature()
            operator, _ = self._actor(uow, context)
            if not operator:
                _denied()
            agent = self.agents.get(uow, agent_id)
            if agent is None or not agent.is_active:
                _denied()
            workspace_ids = self._workspaces(uow, body['workspace_ids'])
            now = _stamp(self.clock.now_iso())
            self._budget(uow, source_id=None, agent_id=agent_id, cost=1, now=now)
            value = self.repo.create_source(uow, agent_id=agent_id, source_kind=body['source_kind'],
                workspace_ids=workspace_ids, registration_ref=registration_ref, now=now,
                source_limit=self.config.observation_max_sources_per_agent,
                installation_limit=self.config.observation_max_sources)
        return dict(source=value)

    def list_sources(self, *, context, agent_id=None, after=None, limit=100):
        self._page(after, limit)
        if agent_id is not None:
            check.identity(agent_id, 'agent_id')
        with self.factory.unit_of_work(write=False) as uow:
            operator, actor_id = self._actor(uow, context)
            if not operator:
                if agent_id is not None and agent_id != actor_id:
                    _denied()
                agent_id = actor_id
            items = self.repo.list_sources(uow, agent_id=agent_id, after=after, limit=limit + 1)
        return dict(items=items[:limit], next_after=items[limit - 1]['source_id'] if len(items) > limit else None)

    def get_source(self, *, context, source_id):
        with self.factory.unit_of_work(write=False) as uow:
            source = self._source(uow, context, source_id)
        return dict(source=source)

    def update_source(self, *, context, source_id, body):
        check.fields(body, ('expected_revision',), ('workspace_ids', 'enabled'))
        revision = check.number(body['expected_revision'])
        if len(body) == 1:
            check.invalid()
        if 'enabled' in body and type(body['enabled']) is not bool:
            check.invalid('enabled')
        with self.factory.unit_of_work() as uow:
            source = self._source(uow, context, source_id, operator_only=True)
            ids = self._workspaces(uow, body['workspace_ids']) if 'workspace_ids' in body else None
            now = _stamp(self.clock.now_iso())
            self._budget(uow, source_id=source_id, agent_id=source['agent_id'], cost=1, now=now)
            value = self.repo.update_source(uow, source_id=source_id, expected_revision=revision,
                                           workspace_ids=ids, enabled=body.get('enabled'), now=now)
        return dict(source=value)

    def revoke_source(self, *, context, source_id, body):
        check.fields(body, ('expected_revision',))
        revision = check.number(body['expected_revision'])
        with self.factory.unit_of_work() as uow:
            self._source(uow, context, source_id, operator_only=True)
            value = self.repo.revoke_source(uow, source_id=source_id, expected_revision=revision,
                                           now=_stamp(self.clock.now_iso()))
        return dict(source=value)

    def create_instance(self, *, context, source_id, body):
        check.fields(body, ('expected_revision', 'workspace_id', 'external_instance_ref'))
        revision = check.number(body['expected_revision'])
        workspace = check.identity(body['workspace_id'], 'workspace_id')
        external_ref = check.opaque(body['external_instance_ref'], 'external_instance_ref')
        with self.factory.unit_of_work() as uow:
            self._feature()
            source = self._source(uow, context, source_id, available=True)
            now = _stamp(self.clock.now_iso())
            self._budget(uow, source_id=source_id, agent_id=source['agent_id'], cost=1, now=now)
            value = self.repo.create_instance(uow, source_id=source_id, expected_revision=revision,
                workspace_id=workspace, external_instance_ref=external_ref, now=now,
                instance_limit=self.config.observation_max_instances)
        return dict(instance=value)

    def _instance_change(self, method, *, context, source_id, observed_instance_id, body):
        check.fields(body, ('expected_revision', 'expected_generation'))
        revision = check.number(body['expected_revision'])
        generation = check.number(body['expected_generation'], 'generation')
        check.identity(observed_instance_id, 'observed_instance_id')
        with self.factory.unit_of_work() as uow:
            if method == 'rotate_instance':
                self._feature()
            source = self._source(uow, context, source_id, available=method == 'rotate_instance')
            now = _stamp(self.clock.now_iso())
            if method == 'rotate_instance':
                self._budget(uow, source_id=source_id, agent_id=source['agent_id'], cost=1, now=now)
            value = getattr(self.repo, method)(uow, source_id=source_id, expected_revision=revision,
                observed_instance_id=observed_instance_id, expected_generation=generation, now=now)
        return dict(instance=value)

    def rotate_instance(self, **kwargs):
        return self._instance_change('rotate_instance', **kwargs)

    def retire_instance(self, **kwargs):
        return self._instance_change('retire_instance', **kwargs)

    def list_instances(self, *, context, source_id, after=None, limit=100):
        self._page(after, limit)
        with self.factory.unit_of_work(write=False) as uow:
            self._source(uow, context, source_id)
            items = self.repo.list_instances(uow, source_id=source_id, after=after, limit=limit + 1)
        return dict(items=items[:limit], next_after=items[limit - 1]['observed_instance_id'] if len(items) > limit else None)

    def issue_token(self, *, context, source_id, body):
        check.fields(body, ('expected_revision', 'instance_grants'), ('replaces_token_id',))
        revision = check.number(body['expected_revision'])
        grants = check.instance_grants(body['instance_grants'])
        previous = body.get('replaces_token_id')
        if previous is not None:
            check.identity(previous, 'replaces_token_id')
        token = generate_observation_token()
        with self.factory.unit_of_work() as uow:
            self._feature()
            source = self._source(uow, context, source_id, available=True)
            subject = self.agents.get(uow, source['agent_id'])
            if not PermissionSet(subject.permissions).allows('observations', 'publish'):
                _denied()
            now = _stamp(self.clock.now_iso())
            self._budget(uow, source_id=source_id, agent_id=source['agent_id'], cost=1, now=now)
            expires_at = (_time(now) + timedelta(minutes=15)).isoformat(timespec='microseconds').replace('+00:00', 'Z')
            # A lost issuance response is recovered by listing/revoking token IDs,
            # never by persisting or retrieving the bearer. Renewal is atomic.
            if previous is not None:
                self.repo.revoke_token(uow, source_id=source_id, token_id=previous, now=now)
            value = self.repo.issue_token(uow, source_id=source_id, expected_revision=revision,
                token_hash=hash_observation_token(token), instance_grants=grants,
                issuer_agent_id=context.actor_agent_id, now=now, expires_at=expires_at,
                max_live=self.config.observation_max_tokens_per_source)
        return dict(token=token, credential={key: item for key, item in value.items() if key != 'token_hash'})

    def list_tokens(self, *, context, source_id, after=None, limit=100):
        self._page(after, limit)
        with self.factory.unit_of_work(write=False) as uow:
            self._source(uow, context, source_id)
            items = self.repo.list_tokens(uow, source_id=source_id, after=after, limit=limit + 1)
        return dict(items=items[:limit], next_after=items[limit - 1]['token_id'] if len(items) > limit else None)

    def revoke_token(self, *, context, source_id, token_id):
        check.identity(token_id, 'token_id')
        with self.factory.unit_of_work() as uow:
            self._source(uow, context, source_id)
            value = self.repo.revoke_token(uow, source_id=source_id, token_id=token_id,
                                          now=_stamp(self.clock.now_iso()))
        return dict(credential={key: item for key, item in value.items() if key != 'token_hash'})

    @staticmethod
    def _publish_authority(facts, reports, now):
        if facts is None:
            _denied()
        token, source, agent = facts['token'], facts['source'], facts['agent']
        if (token['audience'] != 'observations.publish' or token['revoked_at']
                or token['expires_at'] <= now or not source['enabled'] or source['revoked_at']
                or token['source_revision'] != source['revision'] or not agent['is_active']
                or agent.get('deleted_at') or not agent.get('api_key_hash')
                or not PermissionSet(agent['permissions']).allows('observations', 'publish')):
            _denied()
        for report in reports:
            instance = facts['instances'].get(report.observed_instance_id)
            grant = facts['grants'].get(report.observed_instance_id)
            if (report.source_id != source['source_id'] or instance is None or grant is None
                    or instance['source_id'] != source['source_id']
                    or instance['workspace_id'] not in source['allowed_workspace_ids']
                    or grant['workspace_id'] != instance['workspace_id']):
                _denied()
            if not report.generation == grant['generation'] == instance['generation']:
                _conflict()

    def publish(self, *, token, payload):
        if not is_well_formed_observation_token(token):
            _denied()
        values = check.reports(payload)
        # Protocol defaults/bounds stay stable across policy changes. Current
        # max-TTL and clock policy apply only after exact replay detection.
        reports = [parse_report(value) for value in values]
        if len({report.observed_instance_id for report in reports}) != len(reports):
            check.invalid('duplicate_instance')
        # Defaults and UTC precision can expand a near-limit input. Refuse the
        # canonical size here, before a SQLite CHECK could become a 503.
        check.reports({'reports': [report.to_dict() for report in reports]})
        hashes = [report_hash(report) for report in reports]
        receipts = []
        with self.factory.unit_of_work() as uow:
            self._feature()
            now = _stamp(self.clock.now_iso())
            facts = self.repo.get_publish_facts(uow, token_hash=hash_observation_token(token))
            self._publish_authority(facts, reports, now)
            self._budget(uow, source_id=facts['source']['source_id'], agent_id=facts['source']['agent_id'],
                         cost=len(reports), now=now)
            maximum = self.config.observation_max_valid_for_seconds
            limits = ObservationLimits(default_valid_for_seconds=min(90, maximum),
                max_valid_for_seconds=maximum,
                future_tolerance_seconds=self.config.observation_future_tolerance_seconds)
            for report, digest in zip(reports, hashes, strict=True):
                replay = self.repo.check_sequence(uow, observed_instance_id=report.observed_instance_id,
                    generation=report.generation, sequence=report.sequence, report_hash=digest)
                if replay is not None:
                    receipts.append(dict(replay, replayed=True))
                    continue
                freshness = compute_freshness(report, received_at=now, limits=limits)
                previous = facts['heads'].get(report.observed_instance_id)
                data = report.to_dict()
                material = previous is None or any(previous.get(key) != data.get(key)
                    for key in ('state', 'evidence', 'reason_code', 'reason_text'))
                completion = (report.current_completion_ref is not None and (previous is None
                    or previous.get('last_completion_ref') != report.current_completion_ref))
                receipt = self.repo.store_report(uow, report=data, report_hash=digest,
                    source_revision=facts['source']['revision'], publisher_token_id=facts['token']['token_id'],
                    received_at=freshness.received_at, valid_until=freshness.valid_until)
                if material or completion:
                    self.events.emit(uow, workspace_id=facts['instances'][report.observed_instance_id]['workspace_id'],
                        stream='workspace', type='observation.completion' if completion else 'observation.activity',
                        actor_agent_id=facts['source']['agent_id'], visibility='private',
                        target=json.dumps({'strategy': 'direct', 'agent_id': facts['source']['agent_id']}),
                        payload=dict(receipt, state=report.state, evidence=report.evidence,
                            source_id=report.source_id, reason_code=report.reason_code,
                            observed_at=report.observed_at,
                            source_revision=facts['source']['revision'],
                            publisher_token_id=facts['token']['token_id'],
                            completion_ref=report.current_completion_ref if completion else None,
                            observational_only=True))
                receipts.append(dict(receipt, replayed=False))
            # Event history has independent age and cardinality limits. Never
            # remove current head sequence/hash barriers as part of retention.
            cutoff = (_time(now) - timedelta(days=self.config.observation_event_retention_days)).isoformat(
                timespec='microseconds').replace('+00:00', 'Z')
            self.repo.prune_events(uow, cutoff=cutoff, max_events=self.config.observation_max_events, limit=500)
        # Exiting the UoW (including COMMIT) precedes acknowledgement.
        return dict(receipts=receipts)

    def read(self, *, context, agent_id=None, workspace_id=None, source_id=None, after=None, limit=100):
        self._page(after, limit)
        for value in (agent_id, workspace_id, source_id):
            if value is not None:
                check.identity(value)
        with self.factory.unit_of_work(write=False) as uow:
            operator, actor_id = self._actor(uow, context)
            if not operator:
                if agent_id is not None and agent_id != actor_id:
                    _denied()
                agent_id = actor_id
            if source_id is not None:
                self._source(uow, context, source_id)
            now, config = _stamp(self.clock.now_iso()), deepcopy(self.config)
            rows = self.repo.list_current(uow, agent_id=agent_id, workspace_id=workspace_id,
                source_id=source_id, after=after, limit=limit + 1)
            items = self._project_current(uow, rows[:limit], now, config)
        return dict(items=items, next_after=items[-1]['observed_instance_id'] if len(rows) > limit else None,
                    observed_at=now, feature_enabled=config.feature_observations)

    @staticmethod
    def _refresh(items, now):
        deadline = _time(now) + timedelta(seconds=15)
        for item in items:
            head = item['last_report']
            if item['freshness'] == 'current' and head is not None:
                deadline = min(deadline, _time(head['valid_until']))
        return dict(next_refresh_at=deadline.isoformat(timespec='microseconds').replace('+00:00', 'Z'),
                    refresh_after_seconds=max(0.0, (deadline - _time(now)).total_seconds()))

    def _project_current(self, uow, rows, now, config):
        # Authentication and scope filtering precede this single passive batch.
        # Keep native metadata and observation heads in the same SQLite snapshot.
        facts = (self.correlations.load(uow, observed_instance_ids=[
            row['instance']['observed_instance_id'] for row in rows])
            if self.correlations is not None and config.feature_observations else {})
        return [self._project(dict(row, correlation=facts.get(
            row['instance']['observed_instance_id'])), now, config) for row in rows]

    def get_instance(self, *, context, observed_instance_id):
        check.identity(observed_instance_id, 'observed_instance_id')
        with self.factory.unit_of_work(write=False) as uow:
            operator, actor_id = self._actor(uow, context)
            row = self.repo.get_current(uow, observed_instance_id=observed_instance_id,
                                       agent_id=None if operator else actor_id)
            if row is None:
                raise OktoNexusError(ErrorCode.NOT_FOUND, 'Observation instance is unavailable.', {})
            now, config = _stamp(self.clock.now_iso()), deepcopy(self.config)
            item = self._project_current(uow, [row], now, config)[0]
        return dict(item=item, observed_at=now, feature_enabled=config.feature_observations,
                    **self._refresh([item], now))

    def summary(self, *, context, agent_id=None, workspace_id=None, source_id=None):
        deadline = time.monotonic() + 5.0
        filters = {key: value for key, value in dict(agent_id=agent_id,
            workspace_id=workspace_id, source_id=source_id).items() if value is not None}
        for value in filters.values():
            check.identity(value)
        with self.factory.unit_of_work(write=False) as uow:
            operator, actor_id = self._actor(uow, context)
            if not operator:
                if agent_id is not None and agent_id != actor_id:
                    _denied()
                agent_id = actor_id
            if source_id is not None:
                self._source(uow, context, source_id)
            now, config = _stamp(self.clock.now_iso()), deepcopy(self.config)
            rows = self.repo.all_current(uow, agent_id=agent_id, workspace_id=workspace_id, source_id=source_id)
            items = [self._project(row, now, config) for row in rows]
            if time.monotonic() >= deadline:
                raise OktoNexusError('OBSERVATION_QUERY_BUDGET', 'Observation summary exceeded its processing budget.', {})
        def empty():
            return dict(total_instances=0,
                activity=dict(working=0, idle=0, blocked=0, unknown=0),
                freshness=dict(current=0, stale=0, unknown=0, unavailable=0))
        total, groups = empty(), {}
        for item in items:
            group = groups.setdefault(item['agent_id'], dict(agent_id=item['agent_id'], **empty()))
            for target in (total, group):
                target['total_instances'] += 1
                target['activity'][item['activity_state']] += 1
                target['freshness'][item['freshness']] += 1
        if time.monotonic() >= deadline:
            raise OktoNexusError('OBSERVATION_QUERY_BUDGET', 'Observation summary exceeded its processing budget.', {})
        return dict(version=1, filters=filters, feature_enabled=config.feature_observations,
            observed_at=now, **total, agents=[groups[key] for key in sorted(groups)],
            **self._refresh(items, now))

    @staticmethod
    def _head_expired(head, now, *, allow_unproven=False):
        """Validate temporal facts once even when only historical metadata is needed."""
        expired = False
        if head is not None:
            received, valid_until = _time(head['received_at']), _time(head['valid_until'])
            if valid_until <= received:
                raise ValueError('Observation receipt timestamps are inconsistent.')
            if head['observed_at'] is None and not allow_unproven:
                raise ValueError('Observation time is missing.')
            if head['observed_at'] is not None:
                _time(head['observed_at'])
            if head.get('last_completion_received_at') is not None:
                _time(head['last_completion_received_at'])
            expired = valid_until <= _time(now)
        return expired

    @staticmethod
    def _project(row, now, config):
        now = _stamp(now)
        instance, source, agent, head = (row[key] for key in ('instance', 'source', 'agent', 'head'))
        expired = ObservationService._head_expired(head, now, allow_unproven=row.get('historical_unproven', False))
        unavailable = (not config.feature_observations or not source['enabled'] or source['revoked_at']
            or not agent['is_active'] or agent.get('deleted_at') or not agent.get('api_key_hash')
            or not PermissionSet(agent['permissions']).allows('observations', 'publish')
            or instance['workspace_id'] not in source['allowed_workspace_ids']
            or head is not None and (row['publisher_revoked'] or head['source_revision'] != source['revision']
                or head['generation'] != instance['generation']))
        freshness = ('unavailable' if unavailable else 'unknown' if head is None
                     else 'stale' if expired else 'current')
        source_received_at = row.get('source_last_received_at')
        view = dict(observed_instance_id=instance['observed_instance_id'], source_id=source['source_id'],
            agent_id=source['agent_id'], workspace_id=instance['workspace_id'], generation=instance['generation'],
            external_instance_ref=instance['external_instance_ref'], source_kind=source['source_kind'],
            source_revision=source['revision'], freshness=freshness,
            activity_state=head['state'] if head is not None and freshness == 'current' else 'unknown',
            source_last_received_at=source_received_at,
            source_continuity='unknown' if source_received_at is None else 'delayed'
                if (_time(now) - _time(source_received_at)).total_seconds() > config.observation_source_stale_seconds
                else 'recent',
            last_report=None if head is None else {key: head.get(key) for key in (
                'sequence', 'state', 'evidence', 'observed_at', 'received_at', 'valid_until',
                'reason_code', 'reason_text', 'current_completion_ref',
                'last_completion_ref', 'last_completion_received_at')},
            observational_only=True, canonical_session_ref=None)
        # Local import avoids a cycle with the correlation write service, which
        # uses this service's timestamp and current-observation validation.
        from .observation_correlation_view import attach_canonical
        return attach_canonical(view, row.get('correlation'))
