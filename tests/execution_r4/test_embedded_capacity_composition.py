"""Embedded host composes the Core capacity port without a harness launch."""
import asyncio
from dataclasses import replace

import pytest
from nexus_connector_core import (CAPACITY_CONTRACT_REVISION, CapacityRequest, CapacityScope, CoreError)
from okto_nexus.bootstrap.runtime_host import EmbeddedRuntimeHost


class Authority:
    async def check_capacity_scope(self, request, *, action):
        return 'AVAILABLE'


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
