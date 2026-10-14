"""Capacity observations use current Server binding/lease/owner authority."""
from dataclasses import replace
import asyncio
import time

import pytest
from nexus_connector_core import CAPACITY_CONTRACT_REVISION, CapacityRequest, CapacityScope

from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from test_embedded_dispatch import connected_local, local_setup, admit, wait_receipt


def request(setup, binding, *, scope=None, unit='new_session'):
    deps, app, *_ = setup
    owner = app.state.embedded_dispatch_owner
    if scope is None:
        _, revisions, _ = current_agent_revisions(deps.connection_factory, agent_id='subject')
        scope = dict(server_id=owner.channel.server_id, executor_id=owner.channel.executor_id,
            agent_id='subject', binding_id=binding['binding_id'], workspace_id=binding['workspace_id'],
            workspace_binding_id=binding['workspace_binding_id'], session_id='capacity-proposed-session',
            session_owner_generation=1, authorization_revision=revisions.authorization,
            configuration_revision=revisions.configuration, credential_epoch=revisions.credential_epoch,
            binding_revision=binding['binding_revision'])
    return CapacityRequest(CAPACITY_CONTRACT_REVISION, 'capacity-attempt',
        CapacityScope(**scope, connection_generation=owner.channel.connection_generation, boot_id=owner.capacity_boot_id),
        unit, 'sha256:' + 'a' * 64, 10000)


def check(setup, req, action='reserve'):
    _, app, client, *_ = setup
    async def run():
        return await app.state.embedded_dispatch_owner.check_capacity_scope(req, action=action)
    return client.portal.call(run)


def test_cold_capacity_uses_approved_binding_without_creating_session_or_grant(connected_local):
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    req = request(setup, binding)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = tuple(uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
            for table in ('execution_operations', 'execution_sessions', 'runtime_execution_grants'))
    assert check(setup, req) == 'AVAILABLE'
    owner = app.state.embedded_dispatch_owner
    owner.host.capacity_enabled = True
    async def reserve():
        port = await owner.execution_capacity()
        held = await port.try_reserve_capacity(req)
        assert held.state == 'HELD'
        return await port.release_capacity(req, held.reservation_id, 'LOST')
    assert client.portal.call(reserve).state == 'RELEASED'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        after = tuple(uow.connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
            for table in ('execution_operations', 'execution_sessions', 'runtime_execution_grants'))
    assert after == before and native.opens == 0


def test_capacity_rejects_cross_scope_and_stale_revisions_without_changing_other_agents(connected_local):
    setup, binding, native = connected_local
    req = request(setup, binding)
    for field, value in (('server_id', 'foreign'), ('executor_id', 'foreign'), ('agent_id', 'operator'),
            ('binding_id', 'foreign'), ('workspace_id', 'foreign'), ('workspace_binding_id', 'foreign'),
            ('credential_epoch', 999), ('authorization_revision', 999), ('configuration_revision', 999),
            ('binding_revision', 999), ('session_owner_generation', 999), ('connection_generation', 999)):
        assert check(setup, replace(req, scope=replace(req.scope, **{field: value}))) != 'AVAILABLE', field
    assert check(setup, req) == 'AVAILABLE' and native.opens == 0


def test_historical_recovery_survives_subject_revocation_but_not_host_replacement(connected_local):
    setup, binding, _ = connected_local
    deps, app, *_ = setup
    req = request(setup, binding)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='subject'")
    assert check(setup, req) == 'NOT_AUTHORIZED'
    assert check(setup, req, 'get') == check(setup, req, 'release') == 'AVAILABLE'
    authority = app.state.embedded_dispatch_owner.capacity_authority
    original = authority.channel
    authority.channel = replace(original, connection_id='stale-owner')
    try:
        assert check(setup, req, 'get') == 'NOT_AUTHORIZED'
    finally:
        authority.channel = original


def test_capacity_requires_fresh_inventory_and_applied_session_lease(connected_local):
    setup, binding, native = connected_local
    deps, app, *_ = setup
    owner = app.state.embedded_dispatch_owner
    req = request(setup, binding)
    assert check(setup, req) == 'AVAILABLE'
    fresh_key = (owner.channel.server_id, owner.channel.executor_id)
    fresh = owner.inventory.fresh[fresh_key]
    owner.inventory.fresh[fresh_key] = (fresh[0], time.monotonic() - 121)
    try:
        assert check(setup, req) == 'STALE_OBSERVATION'
    finally:
        owner.inventory.fresh[fresh_key] = fresh
    assert check(setup, replace(req, unit='next_turn')) == 'RECOVERING'
    opened = admit(setup, binding, 'capacity-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    existing = request(setup, binding, scope=opened['scope'], unit='next_turn')
    assert check(setup, existing) == 'AVAILABLE'
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at=? WHERE grant_id IN "
            "(SELECT grant_id FROM execution_leases WHERE session_id=?)", (deps.clock.now_iso(), opened['session_id']))
    # The running owner's renewal worker may already have observed revocation
    # and entered containment before this probe. Neither state permits work.
    assert check(setup, existing) in ('NOT_AUTHORIZED', 'RECOVERING') and native.opens == 1
