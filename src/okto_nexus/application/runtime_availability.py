"""Application facade for embedded/remote capacity ports and scoped wakeups.

This registry contains expiring observations, never ownership of work. Durable
attempts belong to the scheduler and reservations to Core. Adapters register
only authenticated connection owners; the facade knows no socket or database.
"""
from dataclasses import dataclass, field
import time

from nexus_connector_core import CoreError
from nexus_connector_core.capacity import CAPACITY_REASONS

from .execution_leases import ExecutionChannel
from .capacity_observations import CapacityObservations


@dataclass(eq=False)
class CapacityHost:
    channel: ExecutionChannel
    port: object
    boot_id: str | None = None
    observations: dict = field(default_factory=dict)
    diagnostic_generation: int = 0
    diagnostic_revision: int = 0
    diagnostic_inflight: int = 0


class RuntimeAvailabilityService:
    def __init__(self, *, enabled=False, monotonic=time.monotonic, wake=lambda: None,
                 max_hosts=1024, max_bindings=256):
        if (type(enabled) is not bool or any(type(n) is not int or n <= 0
                                           for n in (max_hosts, max_bindings))):
            raise ValueError('Invalid capacity registry limits.')
        self.enabled, self.monotonic, self.wake = enabled, monotonic, wake
        self.max_hosts, self.max_bindings = max_hosts, max_bindings
        self._hosts = {}
        self.diagnostics = CapacityObservations(monotonic=monotonic)

    def register(self, channel, port):
        if not self.enabled:
            raise CoreError('CAPACITY_PROTOCOL_UNSUPPORTED', 'runtime_availability')
        key = (channel.server_id, channel.executor_id)
        old = self._hosts.get(key)
        if old is not None and (old.channel.connection_generation > channel.connection_generation
                or old.channel.connection_generation == channel.connection_generation
                and old.channel.connection_id != channel.connection_id):
            raise CoreError('STALE_OBSERVATION', 'capacity_owner')
        if old is None and len(self._hosts) >= self.max_hosts:
            raise CoreError('CAPACITY_EXCEEDED', 'capacity_owners')
        host = CapacityHost(channel, port)
        self.diagnostics.invalidate_host(channel)
        self._hosts[key] = host
        self.wake()
        return host

    def unregister(self, host):
        key = (host.channel.server_id, host.channel.executor_id)
        if self._hosts.get(key) is host:
            self._hosts.pop(key)
            self.diagnostics.invalidate_host(host.channel)
            self.wake()

    def observe(self, host, *, binding_id, boot_id, revision, reason, valid_for_ms):
        if (not isinstance(binding_id, str) or not 0 < len(binding_id) <= 256
                or not isinstance(boot_id, str) or not 0 < len(boot_id) <= 256
                or type(revision) is not int or revision < 0 or reason not in CAPACITY_REASONS
                or type(valid_for_ms) is not int or not 0 <= valid_for_ms <= 60000):
            raise ValueError('Invalid capacity observation.')
        key = (host.channel.server_id, host.channel.executor_id)
        if self._hosts.get(key) is not host:
            return False
        if host.boot_id is not None and host.boot_id != boot_id:
            raise CoreError('STALE_OBSERVATION', 'capacity_boot')
        prior = host.observations.get(binding_id)
        if prior is not None and revision < prior[0]:
            return False
        if prior is None and len(host.observations) >= self.max_bindings:
            raise CoreError('CAPACITY_EXCEEDED', 'capacity_bindings')
        now = self.monotonic()
        host.boot_id = boot_id
        host.diagnostic_revision = max(host.diagnostic_revision, revision)
        host.observations[binding_id] = (revision, reason, now + valid_for_ms / 1000)
        if prior is None or prior[:2] != (revision, reason) or prior[2] <= now:
            self.wake()
        return True

    def current_host(self, server_id, executor_id):
        """Read-only routing fact; callers still need scoped assessment/reserve."""
        return self._hosts.get((server_id, executor_id)) if self.enabled else None

    def _port(self, request, action):
        scope = request.scope
        host = self.current_host(scope.server_id, scope.executor_id)
        if host is None:
            raise CoreError('CAPACITY_PROTOCOL_UNSUPPORTED', 'runtime_availability')
        if action in ('get', 'release'):
            return host.port
        if host.channel.connection_generation != scope.connection_generation or host.boot_id != scope.boot_id:
            raise CoreError('STALE_OBSERVATION', 'runtime_availability')
        if action in ('assess', 'reserve'):
            observation = host.observations.get(scope.binding_id)
            if observation is None or observation[2] <= self.monotonic():
                raise CoreError('STALE_OBSERVATION', 'runtime_availability')
        return host.port

    async def assess_capacity(self, request):
        return await self._call(request, 'assess', 'assess_capacity')

    async def try_reserve_capacity(self, request):
        return await self._call(request, 'reserve', 'try_reserve_capacity')

    async def get_capacity_reservation(self, request):
        return await self._call(request, 'get', 'get_capacity_reservation')

    async def consume_capacity(self, request, reservation_id, admitted):
        return await self._call(request, 'consume', 'consume_capacity', reservation_id, admitted)

    async def release_capacity(self, request, reservation_id, reason):
        return await self._call(request, 'release', 'release_capacity', reservation_id, reason)

    async def _call(self, request, action, method, *args):
        port = self._port(request, action)
        scope = request.scope
        owner = self.current_host(scope.server_id, scope.executor_id)
        mutated = action in ('reserve', 'consume', 'release')
        if mutated:
            owner.diagnostic_generation += 1
            owner.diagnostic_inflight += 1
            self.diagnostics.invalidate_host(owner.channel)
        generation = owner.diagnostic_generation
        try:
            result = await getattr(port, method)(request, *args)
        finally:
            if mutated:
                owner.diagnostic_inflight -= 1
                owner.diagnostic_generation += 1
                if self.current_host(scope.server_id, scope.executor_id) is owner:
                    self.diagnostics.invalidate_host(owner.channel)
        if self.current_host(scope.server_id, scope.executor_id) is not owner:
            # A successful stale reply cannot restore authority. Mutations
            # may have committed and must be queried by their original ID.
            raise CoreError('NEEDS_RECONCILIATION' if mutated else 'STALE_OBSERVATION',
                            'capacity_owner_changed', possible_effect=mutated)
        if not owner.diagnostic_inflight and (mutated or generation == owner.diagnostic_generation):
            from nexus_connector_core import CapacityAssessment, CapacityReservation
            if ((type(result) is CapacityAssessment and result.request_hash == request.request_hash)
                    or (type(result) is CapacityReservation and result.request == request)):
                owner.diagnostic_revision = max(owner.diagnostic_revision, result.capacity_revision)
                self.diagnostics.record(request, result, owner.channel)
        return result

    def capacity_observations(self, agent_id, *, validate=None):
        """No host I/O, mutation, wakeup or capacity promise on an operator read."""
        return self.diagnostics.snapshot(agent_id, self.current_host, validate=validate)
