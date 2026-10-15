import asyncio
from types import SimpleNamespace

from okto_nexus.application.runtime_availability import RuntimeAvailabilityService
from okto_nexus.bootstrap.embedded_capacity import EmbeddedCapacityPublication
from test_capacity_link import CHANNEL


def test_close_during_lazy_port_composition_does_not_reregister_retired_owner():
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        registry = RuntimeAvailabilityService(enabled=True)
        class Service:
            async def expire_unconsumed(self, **kwargs):
                return 0
            async def observe_capacity_revision(self):
                return 1
        async def service():
            entered.set()
            await release.wait()
            return Service()
        owner = SimpleNamespace(channel=CHANNEL, deps=SimpleNamespace(runtime_availability=registry),
            capacity_boot_id='owner', host=SimpleNamespace(capacity_enabled=True),
            _stopping=asyncio.Event(), execution_capacity=service)
        publication = EmbeddedCapacityPublication(owner)
        publication.bindings = lambda: {'binding': 'STALE_OBSERVATION'}
        publication.tick()
        await entered.wait()
        closing = asyncio.create_task(publication.close())
        await asyncio.sleep(0)
        assert not closing.done()
        release.set()
        await closing
        publication.tick()
        assert publication.registration is None
        assert registry.current_host(CHANNEL.server_id, CHANNEL.executor_id) is None
    asyncio.run(run())
