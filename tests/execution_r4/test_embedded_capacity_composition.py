"""Embedded host composes the Core capacity port without a harness launch."""
import asyncio
from dataclasses import replace

import pytest
from nexus_connector_core import (CAPACITY_CONTRACT_REVISION, CapacityRequest, CapacityScope, CoreError)
from okto_nexus.bootstrap.runtime_host import EmbeddedRuntimeHost


class Authority:
    async def check_capacity_scope(self, request, *, action):
        return 'AVAILABLE'


def test_slow_retiring_observer_does_not_block_another_capacity_namespace(tmp_path):
    async def run():
        entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        class SlowAuthority:
            async def check_capacity_scope(self, request, *, action):
                entered.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    await release.wait()
                return 'AVAILABLE'
        host = EmbeddedRuntimeHost(tmp_path / 'core', capacity_enabled=True)
        observer = replacement = None
        try:
            old = await host.capacity_service(server_id='srv', executor_id='exe', boot_id='owner', authority=SlowAuthority())
            observer = asyncio.create_task(old.assess_capacity(request()))
            await entered.wait()
            replacement = asyncio.create_task(host.capacity_service(server_id='srv', executor_id='exe',
                boot_id='replacement', authority=Authority()))
            await cancelled.wait()
            other = await asyncio.wait_for(host.capacity_service(server_id='other', executor_id='exe',
                boot_id='independent', authority=Authority()), 1)
            assert other.boot_id == 'independent' and not replacement.done()
        finally:
            release.set()
            await asyncio.gather(*(task for task in (observer, replacement) if task is not None), return_exceptions=True)
            await host.shutdown()
    asyncio.run(run())


def request():
    return CapacityRequest(CAPACITY_CONTRACT_REVISION, 'attempt', CapacityScope(
        'srv', 'exe', 'agent', 'binding', 'workspace', 'wxb', 'session', 1, 1, 1, 1, 1, 1, 'owner'),
        'new_session', 'sha256:' + 'a' * 64, 10_000)


def test_embedded_reservation_is_shared_with_new_owner_and_never_creates_runtime(tmp_path):
    async def run():
        host = EmbeddedRuntimeHost(tmp_path / 'core', max_owned_slots=1, capacity_enabled=True)
        authority = Authority()
        try:
            port = await host.capacity_service(server_id='srv', executor_id='exe', boot_id='owner', authority=authority)
            assert port is await host.capacity_service(server_id='srv', executor_id='exe', boot_id='owner', authority=authority)
            req = request()
            held = await port.try_reserve_capacity(req)
            assert held.state == 'HELD'
            assert host.shutdown_resources() == []
            foreign = replace(req, scope=replace(req.scope, server_id='foreign'))
            assert (await port.try_reserve_capacity(foreign)).reason == 'NOT_AUTHORIZED'
            with pytest.raises(CoreError, match='NOT_AUTHORIZED'):
                await port.release_capacity(foreign, held.reservation_id, 'LOST')
            new = await host.capacity_service(server_id='srv', executor_id='exe', boot_id='new-owner', authority=Authority())
            assert (await port.try_reserve_capacity(req)).reason == 'RECOVERING'
            assert (await new.get_capacity_reservation(req)).state == 'HELD'
            await new.release_capacity(req, held.reservation_id, 'REVOKED')
            req = replace(req, attempt_id='next', scope=replace(req.scope, boot_id='new-owner', session_id='next'))
            assert (await new.try_reserve_capacity(req)).state == 'HELD'
        finally:
            await host.shutdown()
    asyncio.run(run())


def test_embedded_default_does_not_advertise_or_create_capacity_store(tmp_path):
    async def run():
        host = EmbeddedRuntimeHost(tmp_path / 'core')
        with pytest.raises(CoreError, match='CAPACITY_PROTOCOL_UNSUPPORTED'):
            await host.capacity_service(server_id='srv', executor_id='exe', boot_id='owner', authority=Authority())
        assert not (tmp_path / 'core').exists()
        await host.shutdown()
    asyncio.run(run())


@pytest.mark.parametrize('consumed', [False, True])
def test_boot_resource_scan_releases_only_fenced_unconsumed_reservations(tmp_path, monkeypatch, consumed):
    from types import SimpleNamespace
    from nexus_connector_core import CapacityConsumption
    from okto_nexus.bootstrap.embedded_agent_recovery import EmbeddedAgentRecovery
    from okto_nexus.application.execution_leases import ExecutionChannel
    from test_embedded_inventory import app_for
    deps, _ = app_for(tmp_path / 'home')
    async def run():
        host = EmbeddedRuntimeHost(tmp_path / 'core', max_owned_slots=1, capacity_enabled=True)
        req = request()
        port = await host.capacity_service(server_id='srv', executor_id='exe', boot_id='owner', authority=Authority())
        held = await port.try_reserve_capacity(req)
        if consumed:
            await port.consume_capacity(req, held.reservation_id,
                CapacityConsumption('turn', 'sha256:' + 'b' * 64, 'open', 'sha256:' + 'c' * 64))
        owner = SimpleNamespace(host=host, factory=deps.connection_factory, deps=deps,
            channel=ExecutionChannel('srv', 'exe', 'replacement', 2), verify=lambda **kwargs: None)
        recovery = EmbeddedAgentRecovery(owner)
        try:
            if consumed:
                with pytest.raises(CoreError, match='SCOPE_MISMATCH'):
                    await recovery.initialize()
                assert (await port.get_capacity_reservation(req)).state == 'CONSUMED'
            else:
                await recovery.initialize()
                assert recovery.initialized and not recovery.blocked
                assert (await port.get_capacity_reservation(req)).state == 'RELEASED'
        finally:
            await host.shutdown()
    asyncio.run(run())
