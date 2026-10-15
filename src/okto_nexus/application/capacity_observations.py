"""Bounded diagnostic observations; never an admission or resource authority."""
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from nexus_connector_core import CapacityAssessment, CapacityReservation


class CapacityObservationReader(Protocol):
    def capacity_observations(self, agent_id: str, *, validate=None) -> dict: ...


class CapacityObservationScopes(Protocol):
    def current(self, uow, requests: tuple) -> set[str]: ...


class CapacityObservationView:
    def __init__(self, reader: CapacityObservationReader, scopes: CapacityObservationScopes):
        self.reader, self.scopes = reader, scopes

    def read(self, uow, agent_id):
        return self.reader.capacity_observations(agent_id,
            validate=lambda requests: self.scopes.current(uow, requests))


@dataclass(frozen=True)
class Observation:
    request: object
    channel: object
    state: str
    reason: str
    revision: int
    observed: float
    expires: float


class CapacityObservations:
    def __init__(self, *, monotonic, limit=1024):
        if type(limit) is not int or limit < 1:
            raise ValueError('Invalid diagnostic observation limit.')
        self.monotonic, self.limit = monotonic, limit
        self._items = OrderedDict()
        self._lock = Lock()

    @staticmethod
    def key(request):
        s = request.scope
        return (s.server_id, s.executor_id, s.agent_id, s.binding_id, s.workspace_id,
                request.affinity_key, request.unit, s.session_id)

    def invalidate_host(self, channel):
        with self._lock:
            for key in list(self._items):
                if key[:2] == (channel.server_id, channel.executor_id):
                    del self._items[key]

    def record(self, request, result, channel):
        if type(result) is CapacityAssessment and result.request_hash == request.request_hash:
            reason, ttl, revision = result.reason, result.valid_for_ms, result.capacity_revision
            state = ('IDLE_OBSERVED' if request.unit == 'next_turn' else 'OPENING_CAPACITY_OBSERVED') if result.available else (
                'WAITING_CAPACITY' if reason in {'BUSY_AFFINITY', 'POOL_FULL', 'HOST_FULL', 'EARLIER_WORK_PENDING', 'RESERVATION_CONFLICT'} else 'UNKNOWN')
        elif type(result) is CapacityReservation and result.request == request:
            revision = result.capacity_revision
            reason = result.state
            state = {'HELD':'RESERVED', 'CONSUMED':'IN_USE', 'RELEASE_PENDING':'RELEASE_PENDING'}.get(result.state, 'UNKNOWN')
            # An observed release cannot assert that capacity is still free.
            ttl = result.remaining_ms if result.state == 'HELD' else 5000
        else:
            return
        now = self.monotonic()
        value = Observation(request, channel, state, reason, revision, now, now + min(ttl, 5000) / 1000)
        key = self.key(request)
        with self._lock:
            old = self._items.get(key)
            if old and old.channel == channel and old.revision > revision:
                return
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.limit:
                self._items.popitem(last=False)

    def snapshot(self, agent_id, current_host, *, limit=20, validate=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Invalid observation page limit.')
        with self._lock:
            values = [v for v in reversed(self._items.values()) if v.request.scope.agent_id == agent_id][:limit+1]
        current = validate(tuple(v.request for v in values[:limit])) if validate else None
        now = self.monotonic()
        items = []
        for value in values[:limit]:
            request, scope = value.request, value.request.scope
            host = current_host(scope.server_id, scope.executor_id)
            published = host.observations.get(scope.binding_id) if host else None
            fresh = bool(host and host.channel == value.channel and host.boot_id == scope.boot_id
                and published and published[2] > now and published[0] <= value.revision
                and published[1] != 'RECOVERING' and host.diagnostic_revision <= value.revision
                and not host.diagnostic_inflight and value.observed <= now < value.expires
                and (current is None or request.request_hash in current))
            items.append(dict(executor_id=scope.executor_id, binding_id=scope.binding_id,
                workspace_id=scope.workspace_id, session_id=scope.session_id, unit=request.unit,
                context_id=request.affinity_key, state=value.state if fresh else 'UNKNOWN',
                reason=value.reason if fresh else 'STALE_OBSERVATION', age_ms=max(0, round((now-value.observed)*1000)),
                fresh=fresh, valid_for_ms=max(0, int((value.expires-now)*1000)) if fresh else 0))
        return dict(items=items, has_more=len(values)>limit)
