"""Passive canonical reads: real SQLite/MCP, no provider or personal campaign."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from fake_clock import FakeClock
from test_tools_surface import _call
from okto_nexus.adapters.inbound.http.identity_ctx import current_agent
from okto_nexus.adapters.inbound.mcp.server import bootstrap, create_server
from okto_nexus.application.events import EventService
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import ErrorCode, OktoNexusError


NOW = '2026-11-06T12:00:00.000000Z'


@pytest.fixture
def observation(tmp_path):
    deps = bootstrap({'OKTO_NEXUS_HOME': str(tmp_path / 'home')}, [])
    deps.clock = FakeClock(iso=NOW)
    deps.config.feature_harness_integrations = False
    server = create_server(deps)
    with deps.connection_factory.unit_of_work() as uow:
        for actor in ('reader', 'worker', 'stranger'):
            deps.repos.agents.upsert(uow, agent_id=actor)
            deps.repos.agents.set_key_hash(uow, agent_id=actor, api_key_hash='fixture-' + actor)
        for workspace in ('workspace', 'elsewhere'):
            deps.repos.workspaces.upsert(uow, workspace_id=workspace)
    yield SimpleNamespace(deps=deps, server=server)
    deps.connection_factory.close()


def actor_row(observation, actor='reader'):
    deps = observation.deps
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return deps.repos.agents.get(uow, actor)


def read(observation, name, arguments, *, actor='reader', authenticated=None):
    token = current_agent.set(authenticated or actor_row(observation, actor))
    try:
        return _call(observation.server, name, arguments)
    finally:
        current_agent.reset(token)


def seed_handoff(observation, handoff_id='work', *, status='CLAIMED', visibility='eligible'):
    deps = observation.deps
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.handoffs.create(uow, handoff_id=handoff_id, workspace_id='workspace',
            from_agent_id='reader', target=json.dumps({'strategy': 'direct', 'agent_id': 'worker'}),
            visibility=visibility, payload='Private work', status=status, created_at=NOW)
        if status in ('CLAIMED', 'VERIFYING', 'COMPLETED'):
            uow.connection.execute("UPDATE handoffs SET claimed_by='worker',lease_expires_at=? WHERE handoff_id=?",
                ('2020-01-01T00:00:00.000000Z', handoff_id))


def snapshot(deps):
    """Every persisted table, including unrelated work, presence and outboxes."""
    with deps.connection_factory.unit_of_work(write=False) as uow:
        names = [row[0] for row in uow.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: sorted((tuple(row) for row in uow.connection.execute(
            'SELECT * FROM "' + name.replace('"', '""') + '"')), key=repr) for name in names}


def arguments(name, **changes):
    result = dict(workspace_id='workspace', agent_id='reader', passive=True)
    result.update(dict(handoff_id='work') if name == 'handoff_get' else dict(stream='handoff'))
    return result | changes


def event_service(observation, *, waiter=None, authenticated=None):
    deps = observation.deps
    actor = authenticated or actor_row(observation)
    return EventService(connection_factory=deps.connection_factory, events=deps.repos.events,
        agents=deps.repos.agents, clock=deps.clock, config=deps.config, waiter=waiter,
        request_context_provider=lambda: RuntimeRequestContext(actor.agent_id, 'agent_key',
            credential_binding=actor.api_key_hash))


def test_passive_reads_preserve_all_rows_and_do_not_expire_other_handoffs(observation):
    seed_handoff(observation)
    seed_handoff(observation, 'unrelated')
    before = snapshot(observation.deps)
    got = read(observation, 'handoff_get', arguments('handoff_get'))
    assert got['ok'] and got['data']['status'] == 'CLAIMED', got
    assert got['data']['lease_expires_at'].startswith('2020-')
    assert 'payload' not in got['data']  # creator is not the claimant
    for name in ('event_cursor', 'event_get', 'event_wait'):
        response = read(observation, name, arguments(name))
        assert response['ok'], response
    assert snapshot(observation.deps) == before

    # Compatibility: the omitted/default false path still performs maintenance.
    active = arguments('handoff_get')
    active.pop('passive')
    assert read(observation, 'handoff_get', active)['data']['status'] == 'OPEN'
    with observation.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id='unrelated'").fetchone()[0] == 'OPEN'
        assert observation.deps.repos.agents.get(uow, 'reader').last_seen_at == NOW


@pytest.mark.parametrize('name', ['handoff_get', 'event_cursor', 'event_wait', 'event_get'])
def test_passive_read_keeps_actor_binding_and_exclusive_workspace_selector(observation, name):
    seed_handoff(observation)
    before = snapshot(observation.deps)
    forged = read(observation, name, arguments(name, agent_id='worker'))
    assert not forged['ok'] and forged['error']['code'] == 'PERMISSION_DENIED', forged
    mixed = read(observation, name, arguments(name, project_root='workspace'))
    assert not mixed['ok'] and mixed['error']['code'] == 'VALIDATION_ERROR', mixed
    assert snapshot(observation.deps) == before


def test_passive_handoff_visibility_and_verification_remain_canonical(observation):
    seed_handoff(observation, status='VERIFYING')
    deps = observation.deps
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET result=?,acceptance_criteria=?,verify_by=? WHERE handoff_id='work'",
            ('Delivered but not verified', '["reviewed"]', '{"kind":"creator"}'))
    before = snapshot(deps)
    creator = read(observation, 'handoff_get', arguments('handoff_get'))
    assert creator['ok'] and creator['data']['status'] == 'VERIFYING', creator
    assert creator['data']['result'] == 'Delivered but not verified'
    assert creator['data']['verify_by'] == {'kind': 'creator'}
    claimant = read(observation, 'handoff_get', arguments('handoff_get', agent_id='worker'), actor='worker')
    assert claimant['ok'] and claimant['data']['payload'] == 'Private work', claimant
    stranger = read(observation, 'handoff_get', arguments('handoff_get', agent_id='stranger'), actor='stranger')
    assert not stranger['ok'] and stranger['error']['code'] == 'NOT_OWNER', stranger
    assert snapshot(deps) == before


class ControlledWaiter:
    def __init__(self, *, changed):
        self.entered, self.release = Event(), Event()
        self.changed, self.time = changed, 0

    def monotonic(self):
        return self.time

    def snapshot(self):
        return 0

    def wait_for_change(self, token, timeout_s):
        self.entered.set()
        assert self.release.wait(10)
        self.time += timeout_s
        return self.changed


@pytest.mark.parametrize('change', ['key', 'permission', 'method', 'inactive'])
@pytest.mark.parametrize('changed', [True, False], ids=['page', 'timeout'])
def test_wait_revalidates_current_authority_after_parking(observation, change, changed):
    waiter = ControlledWaiter(changed=changed)
    service = event_service(observation, waiter=waiter)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.event_wait, **arguments('event_wait', timeout_seconds=3))
        try:
            assert waiter.entered.wait(10)
            with observation.deps.connection_factory.unit_of_work() as uow:
                sql = {
                    'key': "UPDATE agents SET api_key_hash='rotated' WHERE agent_id='reader'",
                    'permission': "UPDATE agents SET permissions='{\"events\":{\"read\":false}}' WHERE agent_id='reader'",
                    'inactive': "UPDATE agents SET is_active=0 WHERE agent_id='reader'",
                    'method': "INSERT INTO agent_connection_methods(agent_id,method,enabled) VALUES ('reader','mcp',0) ON CONFLICT(agent_id,method) DO UPDATE SET enabled=0",
                }[change]
                uow.connection.execute(sql)
            before = snapshot(observation.deps)
            waiter.release.set()
            with pytest.raises(OktoNexusError) as denied:
                future.result(timeout=10)
            assert denied.value.code == ErrorCode.PERMISSION_DENIED
            assert snapshot(observation.deps) == before
        finally:
            waiter.release.set()


def test_cursor_before_snapshot_and_hidden_completion_are_recoverable(observation):
    seed_handoff(observation, status='OPEN')
    cursor = read(observation, 'event_cursor', arguments('event_cursor'))['data']['cursor']
    deps = observation.deps
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE handoffs SET status='COMPLETED',result='Done' WHERE handoff_id='work'")
        deps.event_emitter.emit(uow, workspace_id='workspace', stream='handoff', type='handoff.completed',
            actor_agent_id='worker', visibility='eligible',
            target=json.dumps({'strategy': 'direct', 'agent_id': 'worker'}), payload={'handoff_id': 'work'})
    before = snapshot(deps)
    page = read(observation, 'event_wait', arguments('event_wait', cursor=cursor,
        filters={'handoff_id': 'work'}, timeout_seconds=0))['data']
    assert {key: page[key] for key in ('events', 'next_cursor', 'has_more', 'timed_out')} == dict(
        events=[], next_cursor=cursor, has_more=False, timed_out=True)
    result = read(observation, 'handoff_get', arguments('handoff_get'))['data']
    assert result['status'] == 'COMPLETED' and result['result'] == 'Done'
    assert snapshot(deps) == before


def test_passive_wait_catches_later_event_without_holding_a_transaction(observation, monkeypatch):
    seed_handoff(observation, status='OPEN', visibility='public')
    deps = observation.deps
    waiter = ControlledWaiter(changed=True)
    service = event_service(observation, waiter=waiter)
    original = deps.connection_factory.unit_of_work
    active = []
    @contextmanager
    def tracked(write=True):
        with original(write=write) as uow:
            active.append(write)
            try:
                yield uow
            finally:
                active.pop()
    monkeypatch.setattr(deps.connection_factory, 'unit_of_work', tracked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.event_wait, **arguments('event_wait', cursor=0,
            filters={'handoff_id': 'work'}, timeout_seconds=3))
        try:
            assert waiter.entered.wait(10)
            assert active == []
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE handoffs SET status='COMPLETED',result='Done' WHERE handoff_id='work'")
                deps.event_emitter.emit(uow, workspace_id='workspace', stream='handoff', type='handoff.completed',
                    actor_agent_id='worker', visibility='public', payload={'handoff_id': 'work'})
            before = snapshot(deps)
            waiter.release.set()
            page = future.result(timeout=10)
            assert not page['timed_out'] and len(page['events']) == 1
            assert page['events'][0]['type'] == 'handoff.completed'
            assert read(observation, 'handoff_get', arguments('handoff_get'))['data']['status'] == 'COMPLETED'
            assert snapshot(deps) == before
        finally:
            waiter.release.set()


def test_strict_passive_values_and_schema_discovery(observation):
    from mcp.server.fastmcp.exceptions import ToolError
    seed_handoff(observation)
    service = event_service(observation)
    for value in ('true', 'false', 0, 1, None, [], {}):
        with pytest.raises(OktoNexusError) as error:
            service.event_wait(**arguments('event_wait', passive=value, timeout_seconds=0))
        assert error.value.code == ErrorCode.VALIDATION_ERROR
    tools = {tool.name: tool for tool in asyncio.run(observation.server.list_tools())}
    for name in ('handoff_get', 'event_cursor', 'event_get', 'event_wait'):
        schema = tools[name].inputSchema
        assert schema['properties']['passive']['type'] == 'boolean'
        assert schema['properties']['passive']['default'] is False
        assert 'project_root' not in schema.get('required', [])
        before = snapshot(observation.deps)
        with pytest.raises(ToolError, match='boolean'):
            read(observation, name, arguments(name, passive='false'))
        assert snapshot(observation.deps) == before
    info = _call(observation.server, 'nexus_info')['data']
    assert info['coordination_observation'] == {'revision': 1, 'passive': True, 'workspace_selector': True}
    assert info['coordination_requests']['observed_at'] == NOW


def test_managed_passive_reads_keep_capability_scope_and_revocation(tmp_path, monkeypatch):
    """Synthetic R4 selection; real capability/lease and HTTP tool checks."""
    from okto_nexus.bootstrap import embedded_inventory
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **_: SimpleNamespace(candidates=()))
    monkeypatch.syspath_prepend(str(Path(__file__).parent / 'execution_r4'))
    from test_mcp_session_capabilities import opening, activate, seed_work, rpc, envelope
    with contextmanager(opening.__wrapped__)(tmp_path, monkeypatch, SimpleNamespace(param=None)) as state:
        capability = activate(state)
        seed_work(state)
        before = snapshot(state[0])
        for name in ('handoff_get', 'event_cursor', 'event_wait'):
            args = dict(workspace_id='ws', agent_id='subject', passive=True)
            args.update(dict(handoff_id='work') if name == 'handoff_get' else dict(stream='handoff'))
            result = envelope(rpc(state, capability['capability'], name, args))
            assert result['ok'], result
            wrong = envelope(rpc(state, capability['capability'], name, args | {'workspace_id': 'elsewhere'}))
            assert not wrong['ok'] and wrong['error']['code'] == 'PERMISSION_DENIED', wrong
        # This fixture runs an independent inventory publisher while its real
        # control link is open. Domain, presence, lease and capability rows must
        # remain unchanged; inventory publication itself is not an MCP read.
        after = snapshot(state[0])
        for table, rows in before.items():
            if not table.startswith('execution_inventory_'):
                assert after[table] == rows, table
        # Exercise the same managed transaction port after a long-poll parks.
        from okto_nexus.application.execution_capabilities import ExecutionCapabilityService
        from okto_nexus.application.execution_tools import ExecutionToolConnectionFactory
        from okto_nexus.domain.execution_principal import current_execution_principal, current_execution_tool
        caps = ExecutionCapabilityService(factory=state[0].connection_factory, access=state[2])
        principal = caps.authenticate_transport(token=capability['capability'], audience='nexus-mcp-session')
        waiter = ControlledWaiter(changed=True)
        service = EventService(connection_factory=ExecutionToolConnectionFactory(state[0].connection_factory, caps),
            events=state[0].repos.events, agents=state[0].repos.agents, clock=state[0].clock,
            config=state[0].config, waiter=waiter)
        def wait():
            principal_token = current_execution_principal.set(principal)
            tool_token = current_execution_tool.set('event_wait')
            try:
                return service.event_wait(workspace_id='ws', agent_id='subject', stream='handoff',
                    passive=True, timeout_seconds=3)
            finally:
                current_execution_tool.reset(tool_token)
                current_execution_principal.reset(principal_token)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(wait)
            try:
                assert waiter.entered.wait(10)
                with state[0].connection_factory.unit_of_work() as uow:
                    uow.connection.execute("UPDATE execution_session_capabilities SET revoked_at='2026-01-01T00:00:00Z'")
                waiter.release.set()
                with pytest.raises(OktoNexusError) as denied:
                    future.result(timeout=10)
                assert denied.value.code == ErrorCode.PERMISSION_DENIED
            finally:
                waiter.release.set()
        assert rpc(state, capability['capability'], 'handoff_get',
            dict(workspace_id='ws', agent_id='subject', handoff_id='work', passive=True)).status_code == 401
