"""Cooperative admission fence and passive, conservative drain observation."""

from __future__ import annotations

import asyncio
import hashlib

from .models import CoreError, SessionKey


_RELEASE_FIELDS = ('server_id', 'executor_id', 'session_id', 'opening_operation_id',
                   'stream_epoch', 'session_owner_generation')


def _release_identity(scope):
    if type(scope) is not dict or any(type(scope.get(name)) is not str
            or not 1 <= len(scope[name]) <= 256 for name in _RELEASE_FIELDS[:-1]):
        return None
    generation = scope.get('session_owner_generation')
    if type(generation) is not int or generation < 1:
        return None
    return tuple(scope[name] for name in _RELEASE_FIELDS)


class CooperativeDrain:
    def drain_revision(self) -> str:
        """Memory token for host aggregation on this owner loop, not authority."""
        self._drain_owner()
        sessions = []
        for key, binding in self._sessions.items():
            sessions.append((key.server_id, key.executor_id, key.session_id,
                binding.opening_operation_id, binding.epoch, binding.closed,
                binding.closing, binding.draining, binding.faulted, binding.stop_observed,
                binding.revoked, binding.lease_cas_pending, binding.lease_hold,
                binding.superseded, binding.normal_lock.locked(), binding.control_lock.locked(),
                len(binding.pending_native_requests), binding.pump_pending, binding.sink_pending,
                binding.sink_sequence, bool(binding.sink_task and not binding.sink_task.done()),
                binding.context.connection_generation, binding.context.session_owner_generation,
                binding.context.authorization_revision, binding.context.configuration_revision))
        def scopes(values):
            return sorted((k.server_id, k.executor_id, k.session_id) for k in values)
        memory = (self._drain_requested, self._kernel.activity_revision,
                  self._kernel.inflight, self._drain_event_revision, sorted(sessions),
                  self._session_tombstones.revision,
                  scopes(self._opening), scopes(self._uncertain_opens),
                  scopes(self._uncertain_launches), scopes(self._late_handles),
                  scopes(self._release_obligations),
                  sum(not task.done() for task in self._release_producers),
                  sum(not task.done() for task in self._cleanup_tasks),
                  sum(not task.done() for task in self._r4_lease_tasks))
        return hashlib.sha256(repr(memory).encode('utf-8')).hexdigest()

    def _drain_owner(self):
        loop = asyncio.get_running_loop()
        owner = self._drain_owner_loop
        if owner is not None and owner is not loop:
            raise CoreError('SCOPE_MISMATCH', 'drain')
        self._drain_owner_loop = loop
        return loop

    def begin_drain(self) -> None:
        """Fence new work on the owner loop; never contain existing work."""
        self._drain_owner()
        self._drain_requested = True
        for attempt in self._opening.values():
            attempt.guard.closed = True

    def _check_drain_admission(self, action: str) -> None:
        self._drain_owner()
        if self._drain_requested and action in {'runtime.open', 'turn.submit', 'turn.steer'}:
            raise CoreError('RUNTIME_DRAINING', 'admission', retry_safe=True)

    async def drain_status(self) -> dict:
        """Observe a point-in-time drain, without polling or closing native peers.

        A single bounded journal read is shared by concurrent/late callers.
        Cancellation never starts another worker while that read is outstanding.
        No receipt, acknowledgement or recovery state is changed by this method.
        """
        self._drain_owner()
        if not self._drain_requested:
            return {'state': 'RUNNING', 'quiescent': False, 'resources': [],
                    'activity_revision': self.drain_revision(), 'owned_sessions': [],
                    'released_sessions': []}
        resources = []
        released = []
        revision = self.drain_revision()

        def add(reason, outcome='BUSY', key=None, **metadata):
            if len(resources) >= 256:
                return
            if key is not None:
                metadata.update(server_id=key.server_id, executor_id=key.executor_id,
                                session_id=key.session_id)
            resources.append({'reason': reason, 'outcome': outcome, **metadata})

        reader = getattr(self._journal, 'drain_snapshot', None)
        facts = None
        if not callable(reader):
            add('JOURNAL_OBSERVATION_UNAVAILABLE', 'UNKNOWN')
        else:
            task = self._drain_read_task
            if task is not None and task.done():
                # A completed read from an abandoned caller is not current.
                if not task.cancelled():
                    task.exception()
                task = None
            if task is None:
                self._drain_read_revision = self.drain_revision()
                task = asyncio.create_task(reader())
                self._drain_read_task = task
                task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            revision = self._drain_read_revision
            try:
                facts = await asyncio.wait_for(asyncio.shield(task), 1.0)
            except TimeoutError:
                add('JOURNAL_OBSERVATION_PENDING', 'UNKNOWN')
            except Exception:
                add('JOURNAL_OBSERVATION_UNAVAILABLE', 'UNKNOWN')
            finally:
                if task.done():
                    self._drain_read_task = None
            if revision != self.drain_revision():
                add('SNAPSHOT_CHANGED', 'UNKNOWN')
        # No await after this point: observe memory fences in the same loop turn.
        if self._kernel.inflight:
            add('JOURNAL_PRODUCER_PENDING')
        for key in self._opening:
            add('OPENING', key=key)
        for key in self._uncertain_opens | self._uncertain_launches.keys():
            add('OPEN_OUTCOME_UNKNOWN', 'UNKNOWN', key)
        for key, binding in self._sessions.items():
            if binding.normal_lock.locked() or binding.control_lock.locked():
                add('COMMAND_IN_FLIGHT', key=key)
            if binding.pending_native_requests:
                add('NATIVE_REQUEST_PENDING', key=key)
            if binding.pump_pending:
                add('EVENT_COMMIT_PENDING', key=key)
            if binding.sink_pending or (binding.sink_task and not binding.sink_task.done()):
                add('EVENT_SINK_PENDING', key=key)
            if binding.lease_cas_pending or binding.lease_hold:
                add('LEASE_RECONCILIATION_PENDING', 'UNKNOWN', key)
            if binding.faulted and not binding.stop_observed:
                add('EVENT_STREAM_UNAVAILABLE', 'UNKNOWN', key)
            if binding.closing and not binding.closed:
                add('CLOSE_PENDING', key=key)
            active = getattr(binding.native, 'active_turn', None)
            if callable(active):
                try:
                    value = active()
                except Exception:
                    value = None
                if value is True:
                    add('NATIVE_TURN_ACTIVE', key=key)
                elif value is not False:
                    add('NATIVE_TURN_UNKNOWN', 'UNKNOWN', key)
        for key in self._release_obligations:
            add('OWNERSHIP_RELEASE_PENDING', key=key)
        if any(not task.done() for task in self._release_producers):
            add('RELEASE_PRODUCER_PENDING')
        for key, record in self._late_handles.items():
            if record.last_state != 'STOPPED':
                add('LATE_NATIVE_HANDLE', 'UNKNOWN', key)
        if any(not task.done() for task in self._cleanup_tasks):
            add('CLEANUP_PENDING')
        if any(not task.done() for task in self._r4_lease_tasks):
            add('LEASE_COMMIT_PENDING')
        if facts is not None:
            for row in facts['operations']:
                key = SessionKey(row['server_id'], row['executor_id'], row['session_id'])
                outcome = 'UNKNOWN' if row['stage'] in {
                    'OUTCOME_UNKNOWN', 'SUBMISSION_STARTED'} or row['action'] is None else 'BUSY'
                add('JOURNAL_OPERATION_PENDING', outcome, key,
                    operation_id=row['operation_id'], stage=row['stage'], action=row['action'])
            for row in facts['claims']:
                key = SessionKey(row['server_id'], row['executor_id'], row['session_id'])
                if key not in self._sessions and key not in self._opening:
                    scope = {name: row.get(name) for name in _RELEASE_FIELDS}
                    scope['opening_operation_id'] = row['operation_id']
                    proof = self._session_tombstones.released_proof(key)
                    identity = _release_identity(scope)
                    # A restart, missing generation, absent/ambiguous stream or
                    # evicted proof stays unknown. Never rewrite durable history.
                    if (proof is not None and identity is not None
                            and identity[3:] == (proof.opening_operation_id,
                                proof.stream_epoch, proof.session_owner_generation)
                            and (proof.sink_sequence is None or any(
                                watermark['server_id'] == key.server_id
                                and watermark['executor_id'] == key.executor_id
                                and watermark['session_id'] == key.session_id
                                and watermark['stream_epoch'] == proof.stream_epoch
                                and watermark['sequence'] <= proof.sink_sequence
                                for watermark in facts['watermarks']))):
                        released.append(scope)
                        continue
                    add('SESSION_RECONCILIATION_PENDING', 'UNKNOWN', key,
                        opening_operation_id=row['operation_id'],
                        stream_epoch=row.get('stream_epoch'),
                        session_owner_generation=row.get('session_owner_generation'))
            for row in facts['streams']:
                key = SessionKey(row['server_id'], row['executor_id'], row['session_id'])
                add('EVENT_ACK_PENDING', key=key, stream_epoch=row['stream_epoch'])
            for row in facts['watermarks']:
                key = SessionKey(row['server_id'], row['executor_id'], row['session_id'])
                binding = self._sessions.get(key)
                if (self._event_sink is not None and binding is not None
                        and binding.epoch == row['stream_epoch']
                        and binding.sink_sequence < row['sequence']):
                    add('EVENT_SINK_PENDING', key=key, stream_epoch=row['stream_epoch'])
            if facts['truncated']:
                add('JOURNAL_OBSERVATION_TRUNCATED', 'UNKNOWN')
        if len(resources) >= 256:
            resources[-1] = {'reason': 'RESOURCE_LIMIT', 'outcome': 'UNKNOWN'}
        state = ('UNKNOWN' if any(row['outcome'] == 'UNKNOWN' for row in resources)
                 else 'BUSY' if resources else 'QUIESCENT')
        owned = [{'server_id': key.server_id, 'executor_id': key.executor_id,
                  'session_id': key.session_id, 'opening_operation_id': binding.opening_operation_id,
                  'stream_epoch': binding.epoch} for key, binding in self._sessions.items()]
        if len(owned) > 256:
            resources = [{'reason': 'RESOURCE_LIMIT', 'outcome': 'UNKNOWN'}]
            state = 'UNKNOWN'
        return {'state': state, 'quiescent': state == 'QUIESCENT', 'resources': resources,
                'activity_revision': revision, 'owned_sessions': owned[:256],
                'released_sessions': released}


def combine_drain_status(reports: list[dict]) -> dict:
    """Combine reports from Core owners of ONE shared journal only.

    The caller must recheck each owner's public drain_revision() after all
    awaits. This pure function supplies no cross-journal or authorization proof.
    Only an exact opening claim retained by one other owner, or a complete
    local eviction proof from that owner, can discharge a claim resource.
    Other resources (including unresolved receipts and ACKs) remain blockers.
    """
    def unknown(reason):
        return {'state': 'UNKNOWN', 'quiescent': False,
                'resources': [{'reason': reason, 'outcome': 'UNKNOWN'}]}
    if type(reports) is not list or len(reports) > 256:
        return unknown('DRAIN_COMPOSITION_UNAVAILABLE')
    owners = {}
    releases = {}
    for index, report in enumerate(reports):
        if (type(report) is not dict or report.get('state') not in {'BUSY', 'UNKNOWN', 'QUIESCENT'}
                or type(report.get('quiescent')) is not bool
                or type(report.get('activity_revision')) is not str
                or len(report['activity_revision']) != 64
                or type(report.get('owned_sessions')) is not list
                or type(report.get('resources')) is not list
                or len(report['owned_sessions']) > 256 or len(report['resources']) > 256
                or report['quiescent'] != (report['state'] == 'QUIESCENT')
                or (report['state'] == 'QUIESCENT' and report['resources'])
                or (report['state'] != 'QUIESCENT' and not report['resources'])):
            return unknown('DRAIN_COMPOSITION_UNAVAILABLE')
        for scope in report['owned_sessions']:
            names = ('server_id', 'executor_id', 'session_id', 'opening_operation_id', 'stream_epoch')
            if type(scope) is not dict or set(scope) != set(names) or any(
                    type(scope.get(name)) is not str or not 1 <= len(scope[name]) <= 256 for name in names):
                return unknown('DRAIN_COMPOSITION_UNAVAILABLE')
            key = tuple(scope[name] for name in names[:3])
            if key in owners:
                return unknown('DRAIN_OWNER_CONFLICT')
            owners[key] = (index, scope['opening_operation_id'])
        released = report.get('released_sessions', [])
        if type(released) is not list or len(released) > 256:
            return unknown('DRAIN_COMPOSITION_UNAVAILABLE')
        for scope in released:
            identity = _release_identity(scope)
            if identity is None or set(scope) != set(_RELEASE_FIELDS):
                return unknown('DRAIN_COMPOSITION_UNAVAILABLE')
            key = identity[:3]
            if key in releases:
                return unknown('DRAIN_OWNER_CONFLICT')
            releases[key] = (index, identity)
    if owners.keys() & releases.keys():
        return unknown('DRAIN_OWNER_CONFLICT')
    resources = []
    for index, report in enumerate(reports):
        for row in report['resources']:
            if (type(row) is not dict or type(row.get('reason')) is not str
                    or row.get('outcome') not in {'BUSY', 'UNKNOWN'}):
                return unknown('DRAIN_COMPOSITION_UNAVAILABLE')
            if row['reason'] == 'SESSION_RECONCILIATION_PENDING':
                key = tuple(row.get(name) for name in ('server_id', 'executor_id', 'session_id'))
                if any(type(value) is not str for value in key):
                    return unknown('DRAIN_COMPOSITION_UNAVAILABLE')
                owner = owners.get(key)
                if owner is not None and owner[0] != index and owner[1] == row.get('opening_operation_id'):
                    continue
                release = releases.get(key)
                if (release is not None and release[0] != index
                        and release[1] == _release_identity(row)):
                    continue
            resources.append(dict(row))
            if len(resources) >= 256:
                return unknown('DRAIN_COMPOSITION_LIMIT')
    state = ('UNKNOWN' if any(row['outcome'] == 'UNKNOWN' for row in resources)
             else 'BUSY' if resources else 'QUIESCENT')
    return {'state': state, 'quiescent': state == 'QUIESCENT', 'resources': resources}
