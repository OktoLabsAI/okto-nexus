"""Compose embedded capacity observations through the application port."""
import asyncio

from nexus_connector_core import CapacityChangePublisher

from ..application.execution_agent_recovery import agent_recovering


class EmbeddedCapacityPublication:
    def __init__(self, owner):
        self.owner = owner
        self.registry = owner.deps.runtime_availability
        self.registration = None
        self.service = None
        self.closed = False
        self.publisher = CapacityChangePublisher(boot_id=owner.capacity_boot_id,
            snapshot=self.snapshot, emit=self.emit)

    def tick(self):
        if not self.closed and self.owner.host.capacity_enabled and self.registry.enabled:
            self.publisher.tick()

    def bindings(self):
        owner, channel = self.owner, self.owner.channel
        with owner.factory.unit_of_work(write=False) as uow:
            owner.verify(uow=uow)
            rows = uow.connection.execute('SELECT b.binding_id,ep.agent_id FROM execution_bindings b '
                'JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id '
                'WHERE b.server_id=? AND b.executor_id=? AND ep.enabled=1 '
                "AND ep.activation_state='approved' ORDER BY b.binding_id LIMIT 257",
                (channel.server_id, channel.executor_id)).fetchall()
            return {row['binding_id']: ('RECOVERING' if owner.failure is not None or agent_recovering(
                uow.connection, channel.server_id, channel.executor_id, row['agent_id'])
                else 'STALE_OBSERVATION') for row in rows}

    async def snapshot(self):
        owner = self.owner
        if self.closed or owner._stopping.is_set():
            raise RuntimeError('Capacity owner is stopping.')
        if self.service is None:
            self.service = await owner.execution_capacity()
        await self.service.expire_unconsumed(limit=128)
        revision = await self.service.observe_capacity_revision()
        bindings = await asyncio.to_thread(self.bindings)
        if self.registration is None and not self.closed and not owner._stopping.is_set():
            self.registration = self.registry.register(owner.channel, self.service)
        return revision, bindings

    async def emit(self, **observation):
        if self.closed or self.owner._stopping.is_set():
            return
        self.registry.observe(self.registration, **observation)

    async def close(self):
        # Remove routing before waiting for the retained observation producer.
        self.closed = True
        if self.registration is not None:
            self.registry.unregister(self.registration)
        await self.publisher.aclose()
