"""An applied renewal refreshes metadata, never capability material or authority."""
# ruff: noqa: F401, F811
import time

import pytest

from okto_nexus.errors import OktoNexusError
from test_session_capabilities import opening, issue, begin, apply_lease, service  # noqa: F401
from test_embedded_dispatch import connected_local, local_setup, qualified_contract, admit, wait_receipt  # noqa: F401
from test_embedded_tools import enable_tools


def metadata_args(state, issued):
    return dict(context=state[3], session_id=issued['scope']['session_id'],
        binding_id=issued['scope']['binding_id'], capability_id=issued['capability_id'],
        request_id='opening-metadata', mcp_url=issued['mcp_url'])


def test_opening_metadata_follows_applied_renewal_without_issuing_or_enabling_actions(opening):
    issued = issue(opening).json()
    begin(opening)
    args = metadata_args(opening, issued)
    authority = service(opening)
    with pytest.raises(OktoNexusError):
        authority.describe_opening_transport(**args)
    leases, _, _, ack = apply_lease(opening)
    with pytest.raises(OktoNexusError):
        authority.describe_opening_transport(**args)  # Issued is not applied.
    leases.applied(ack, channel=opening[5])
    first = authority.describe_opening_transport(**args)
    leases, _, _, renewed = apply_lease(opening, serial=1, purpose='renew', request_id='renew')
    leases.applied(renewed, channel=opening[5])
    current = authority.describe_opening_transport(**args)
    assert current['lease_serial'] == first['lease_serial'] + 1
    assert current['capability_id'] == first['capability_id'] == issued['capability_id']
    assert 'capability' not in current and 0 < current['expires_in'] <= 120
    with pytest.raises(OktoNexusError):
        authority.describe(**args)  # Public metadata still requires READY.
    with pytest.raises(OktoNexusError):
        authority.authorize_call(token=issued['capability'], audience=issued['audience'],
            action='tools/call', expected_scope=issued['scope'])
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_session_capabilities').fetchone()[0] == 1
        assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == 'OPEN_PENDING'


@pytest.mark.parametrize('sql', [
    "UPDATE execution_session_capabilities SET revoked_at='2026-01-01T00:00:00Z'",
    "UPDATE execution_session_capabilities SET valid_until_server='2000-01-01T00:00:00Z'",
    "UPDATE execution_leases SET valid_until_server='2000-01-01T00:00:00Z'",
    "UPDATE runtime_execution_grants SET revoked_at='2026-01-01T00:00:00Z'",
    "UPDATE execution_sessions SET owner_generation=owner_generation+1",
    "UPDATE execution_sessions SET lifecycle_state='FAILED'",
])
def test_opening_metadata_rejects_changed_canonical_authority(opening, sql):
    issued = issue(opening).json()
    begin(opening)
    leases, _, _, ack = apply_lease(opening)
    leases.applied(ack, channel=opening[5])
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute(sql)
    with pytest.raises(OktoNexusError):
        service(opening).describe_opening_transport(**metadata_args(opening, issued))


@pytest.mark.parametrize('local_setup', ['codex_app_server', 'claude_stream'], indirect=True)
def test_local_environment_refreshes_expired_snapshot_before_native_open(connected_local):
    setup, binding, native, vault, environments = enable_tools(connected_local)
    owner = setup[1].state.embedded_dispatch_owner
    original = native.open
    seen = []

    async def delayed(prepared, session_id, context, **kwargs):
        config = owner.tools.configurations[session_id]
        old_material = config['cap']['capability']
        config['deadline'] = time.monotonic() - 1
        # The real environment callback must re-read the real applied lease;
        # no clock sleeps or provider processes are needed for this boundary.
        result = await original(prepared, session_id, context, **kwargs)
        assert config['deadline'] > time.monotonic()
        assert config['cap']['capability'] == old_material
        seen.append(config['cap']['capability_id'])
        return result

    native.open = delayed
    opened = admit(setup, binding, 'expired-local-snapshot', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    assert len(seen) == len(environments) == len(vault.values) == native.opens == 1
    closed = admit(setup, binding, 'refresh-close', 'runtime.close', session_id=opened['session_id'])
    wait_receipt(setup, closed, stages=('SUCCEEDED',))


@pytest.mark.parametrize('change', ['revoked', 'observation_expired'])
def test_authority_is_checked_after_final_materialization_checks(monkeypatch, change):
    import asyncio
    from types import SimpleNamespace
    from nexus_connector_core import CoreError, LaunchIntent
    from okto_nexus.application import execution_local_launch as module
    launch = object.__new__(module.ApprovedLocalLaunch)
    launch.scope = dict(agent_id='subject', workspace_id='workspace')
    launch.candidate = SimpleNamespace(adapter_id='codex_app_server')
    launch.auth_refs = ('mcp-cap:fixture',)
    launch.resolver = None
    launch.record = dict(provider_home=None, configuration=dict(secret_bindings={}))
    trace = []
    launch.check = lambda: trace.append('selection')
    def refresh():
        trace.append('authority')
        if trace.count('authority') == 2:
            if change == 'revoked':
                raise CoreError('AUTH_EXPIRED', 'fixture_canonical_authority')
            return time.monotonic() - 1
        return time.monotonic() + 10
    launch.tools = dict(home=SimpleNamespace(require_current=lambda: trace.append('home')),
        template=None, cap=dict(capability_ref='mcp-cap:fixture', capability='synthetic'),
        deadline=-1, current_transport_deadline=refresh)
    async def materialize(*args, **kwargs):
        trace.append('materialized')
        return {'SYNTHETIC': 'environment'}
    monkeypatch.setattr(module, 'child_environment', materialize)
    prepared = SimpleNamespace(intent=LaunchIntent('subject', 'workspace', 'codex_app_server'),
        secret_refs=launch.auth_refs)
    with pytest.raises(CoreError) as error:
        asyncio.run(launch.environment(prepared))
    assert error.value.code == 'AUTH_EXPIRED'
    assert trace == ['selection', 'home', 'authority', 'materialized', 'selection', 'home', 'authority']
