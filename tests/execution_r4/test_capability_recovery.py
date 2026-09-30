"""Fresh metadata and vaulted material require matching applied Core authority."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from nexus_connector_core import InstallationCandidate, LaunchIntent, OpenOperation, ShutdownPolicy, create_runtime, r4_lease_renew_frame
from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.journal import open_journal
from nexus_connector_core.native_action_bridge import ContextGet

from okto_nexus.application.execution_leases import ExecutionLeaseService
from test_native_actions import opening
from test_mcp_session_capabilities import seed_work
from test_session_capabilities import begin, apply_lease
from test_vertical_inventory import _NativeFactory


@pytest.mark.parametrize('fault', ['none', 'renewed', 'server_revoked', 'local_revoked', 'serial', 'vault_missing'])
@pytest.mark.parametrize('opening', ['strict'], indirect=True)
def test_restored_capability_requires_current_server_and_core_authority(opening, tmp_path, fault):
    from okto_nexus_connector.errors import ConnectorError
    from okto_nexus_connector.identity.vault import RestrictedFileVault
    from okto_nexus_connector.services.session_capabilities import SessionCapabilityOwner
    from okto_nexus_connector.storage.state_store import StateStore
    from okto_nexus_connector.transport.https_client import NexusHTTPClient
    from okto_nexus_connector.transport.native_actions import native_action_bridge
    from nexus_connector_core import CoreError

    deps, app, access, _, _, channel, _, _ = opening
    sent = begin(opening)
    seed_work(opening)
    store = StateStore(tmp_path / 'recovery-state.json')
    vault = RestrictedFileVault(tmp_path, approved=True)
    async def run():
        journal = await open_journal(tmp_path / 'recovery-core.db')
        binary = tmp_path / 'codex.exe'
        candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
        async def environment(_): return {}
        runtime = create_runtime(journal=journal, environment=environment, lease_poll_seconds=3600,
            candidates={candidate.adapter_id: candidate}, workspace_roots={'ws': str(tmp_path)},
            native_factory=_NativeFactory())
        owners = []
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as raw:
                async with NexusHTTPClient('https://127.0.0.1:8202', client=raw) as http:
                    key = app.state.test_agent_keys['subject']
                    args = dict(frame=sent.frame, audience='nexus-native-session',
                        actions=('handoff.get', 'handoff.claim', 'handoff.complete'), require_current=lambda: None)
                    owner = SessionCapabilityOwner(store, vault)
                    owners.append(owner)
                    initial = await owner.reserve(http, key, **args)
                    attempt = await runtime.begin_r4_lease_request(scope=sent.scope, grant_id=sent.grant_id,
                        connection_id=channel.connection_id, connection_generation=channel.connection_generation,
                        purpose='initial')
                    leases = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                        fresh_publications=app.state.inventory_fresh_publications)
                    installed = await runtime.install_r4_lease(attempt,
                        leases.issue(r4_lease_renew_frame(attempt), channel=channel))
                    leases.applied(installed.acknowledgement, channel=channel)
                    context = installed.context
                    prepared = await runtime.prepare(LaunchIntent('subject', 'ws', candidate.adapter_id), context)
                    await runtime.open(OpenOperation(sent.frame['operation_id'], sent.scope['session_id'], 'epoch', prepared), context)
                    with deps.connection_factory.unit_of_work() as uow:
                        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY'")
                    await owner.close()
                    recovered_owner = SessionCapabilityOwner(StateStore(store.path), vault)
                    owners.append(recovered_owner)
                    if fault == 'server_revoked':
                        with deps.connection_factory.unit_of_work() as uow:
                            uow.connection.execute('UPDATE execution_session_capabilities SET revoked_at=?', (deps.clock.now_iso(),))
                    elif fault == 'local_revoked':
                        await runtime.revoke_r4_lease(context, authorization_revision=context.authorization_revision + 1)
                    elif fault == 'serial':
                        service, _, _, ack = apply_lease(opening, serial=1, purpose='renew', request_id='new-serial')
                        service.applied(ack, channel=channel)
                    elif fault == 'renewed':
                        attempt = await runtime.begin_r4_lease_request(scope=sent.scope, grant_id=sent.grant_id,
                            connection_id=channel.connection_id, connection_generation=channel.connection_generation,
                            purpose='renew')
                        renewed = await runtime.install_r4_lease(attempt,
                            leases.issue(r4_lease_renew_frame(attempt), channel=channel))
                        leases.applied(renewed.acknowledgement, channel=channel)
                        context = renewed.context
                        assert context.r4_authority.lease_serial == 2
                    elif fault == 'vault_missing':
                        vault.remove(store.load().session_capabilities[0].secret_handle.removeprefix('vault:'))
                    if fault not in ('none', 'renewed'):
                        with pytest.raises((ConnectorError, CoreError)):
                            await recovered_owner.restore(http, key, runtime=runtime, **args)
                    else:
                        restored = await recovered_owner.restore(http, key, runtime=runtime, **args)
                        assert restored.capability == initial.capability
                        assert restored.capability_id == initial.capability_id
                        assert restored.deadline_monotonic <= context.lease_deadline_monotonic
                        bridge = native_action_bridge(http, restored, runtime, connection_id=channel.connection_id,
                            connection_generation=channel.connection_generation)
                        result = await bridge.invoke(ContextGet('restored-read', sent.scope['session_id'],
                            restored.capability_ref, 'work'), context)
                        assert result['status'] == 'OPEN'
                        assert restored.capability not in store.path.read_text()
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        assert uow.connection.execute('SELECT COUNT(*) FROM execution_session_capabilities').fetchone()[0] == 1
        finally:
            for owner in owners:
                await owner.close()
            await runtime.shutdown(ShutdownPolicy(0, 0))
            await journal.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('fault', ['none', 'reserved', 'other_agent', 'extra', 'duplicate', 'expired', 'renewing', 'renewing_expired'])
def test_metadata_is_authorized_read_only_and_never_returns_secret(opening, fault):
    from fastapi.testclient import TestClient
    from jsonschema import Draft202012Validator
    from test_session_capabilities import issue
    issued = issue(opening).json()
    deps, app, _, _, _, channel, _, _ = opening
    if fault != 'reserved':
        begin(opening)
        service, _, _, ack = apply_lease(opening)
        service.applied(ack, channel=channel)
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY'")
            if fault == 'expired':
                uow.connection.execute("UPDATE execution_session_capabilities SET valid_until_server='2000-01-01T00:00:00+00:00'")
    if fault in ('renewing', 'renewing_expired'):
        apply_lease(opening, serial=1, purpose='renew', request_id='metadata-renewal')
        if fault == 'renewing_expired':
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute("UPDATE execution_leases SET valid_until_server='2000-01-01T00:00:00+00:00' WHERE lease_serial=1")
    params = [('binding_id', 'binding'), ('capability_id', issued['capability_id']), ('request_id', 'metadata-one')]
    if fault == 'extra': params.append(('scope', 'untrusted'))
    if fault == 'duplicate': params.append(('request_id', 'metadata-two'))
    actor = 'other' if fault == 'other_agent' else 'subject'
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = dict(uow.connection.execute('SELECT * FROM execution_session_capabilities').fetchone())
    response = TestClient(app, base_url='https://127.0.0.1:8202').get(
        '/v1/runtime/sessions/' + issued['scope']['session_id'] + '/capability', params=params,
        headers={'Authorization': 'Bearer ' + app.state.test_agent_keys[actor]})
    expected = {'none': 200, 'reserved': 403, 'other_agent': 404, 'extra': 422, 'duplicate': 422, 'expired': 403, 'renewing': 200, 'renewing_expired': 403}
    assert response.status_code == expected[fault], response.text
    assert issued['capability'] not in response.text
    if fault in ('none', 'renewing'):
        body = response.json()
        assert body['request_id'] == 'metadata-one' and body['lease_serial'] == 1
        assert 1 <= body['expires_in'] <= issued['expires_in']
        assert response.headers['cache-control'] == 'no-store'
        schema = json.loads((Path(__file__).parents[2] / 'plans/contratos/http-target.schema.json').read_text())
        Draft202012Validator(dict(schema, **{'$ref': '#/$defs/CapabilityMetadata'})).validate(body)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert dict(uow.connection.execute('SELECT * FROM execution_session_capabilities').fetchone()) == before
