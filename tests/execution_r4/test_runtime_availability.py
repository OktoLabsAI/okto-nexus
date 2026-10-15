import asyncio
from dataclasses import replace

import pytest
from nexus_connector_core import CoreError

from okto_nexus.application.runtime_availability import RuntimeAvailabilityService
from test_capacity_link import CHANNEL, request


def observe(registry, host, **updates):
    return registry.observe(host, **(dict(binding_id='binding', boot_id='owner', revision=1,
        reason='STALE_OBSERVATION', valid_for_ms=30000) | updates))


def test_observations_expire_and_old_owners_cannot_restore_availability():
    now, wakes = [0.], []
    registry = RuntimeAvailabilityService(enabled=True, monotonic=lambda: now[0], wake=lambda: wakes.append(1))
    first = registry.register(CHANNEL, object())
    observe(registry, first)
    assert registry._port(request(), 'assess') is first.port
    count = len(wakes)
    now[0] = 10
    observe(registry, first)
    assert len(wakes) == count
    assert not observe(registry, first, revision=0)
    now[0] = 41
    with pytest.raises(CoreError, match='STALE_OBSERVATION'):
        registry._port(request(), 'reserve')
    second = registry.register(replace(CHANNEL, connection_id='next', connection_generation=2), object())
    assert not observe(registry, first)
    registry.unregister(first)
    assert registry.current_host('srv', 'exe') is second
    # Historical exact-attempt recovery routes to the authenticated new owner.
    assert registry._port(request(), 'get') is second.port
    with pytest.raises(CoreError, match='STALE_OBSERVATION'):
        registry._port(request(), 'consume')
    with pytest.raises(CoreError, match='STALE_OBSERVATION'):
        registry.register(CHANNEL, object())


@pytest.mark.parametrize('action,method', [('assess', 'assess_capacity'), ('reserve', 'try_reserve_capacity'),
    ('get', 'get_capacity_reservation'), ('consume', 'consume_capacity'), ('release', 'release_capacity')])
def test_owner_replacement_during_observation_cannot_return_stale_success(action, method):
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        class Port:
            async def call(self, *args):
                entered.set()
                await release.wait()
                return object()
        setattr(Port, method, Port.call)
        registry = RuntimeAvailabilityService(enabled=True)
        first = registry.register(CHANNEL, Port())
        observe(registry, first)
        extra = ('reservation', 'proof') if action in ('consume', 'release') else ()
        task = asyncio.create_task(getattr(registry, method)(request(), *extra))
        await entered.wait()
        registry.register(replace(CHANNEL, connection_id='next', connection_generation=2), Port())
        release.set()
        mutated = action in ('reserve', 'consume', 'release')
        with pytest.raises(CoreError, match='NEEDS_RECONCILIATION' if mutated else 'STALE_OBSERVATION') as error:
            await task
        assert error.value.possible_effect == mutated
    asyncio.run(run())


def test_unnegotiated_hosts_and_boot_changes_are_not_silently_accepted():
    registry = RuntimeAvailabilityService()
    with pytest.raises(CoreError, match='CAPACITY_PROTOCOL_UNSUPPORTED'):
        registry.register(CHANNEL, object())
    registry.enabled = True
    first = registry.register(CHANNEL, object())
    observe(registry, first)
    with pytest.raises(CoreError, match='STALE_OBSERVATION'):
        observe(registry, first, boot_id='unexpected-new-clock')


def test_registry_bounds_memory_without_rejecting_owner_replacement_or_existing_binding_refresh():
    registry = RuntimeAvailabilityService(enabled=True, max_hosts=1, max_bindings=1)
    first = registry.register(CHANNEL, object())
    observe(registry, first)
    assert observe(registry, first, revision=2)
    with pytest.raises(CoreError, match='CAPACITY_EXCEEDED'):
        observe(registry, first, binding_id='second')
    with pytest.raises(CoreError, match='CAPACITY_EXCEEDED'):
        registry.register(replace(CHANNEL, executor_id='other'), object())
    current = registry.register(replace(CHANNEL, connection_id='new', connection_generation=2), object())
    assert observe(registry, current)
    assert len(current.observations) == 1
