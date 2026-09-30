"""Public capability reservation and the separate active-use authority gate.

The shared fixture seeds selection metadata and uses synthetic qualification;
admission, dispatch, authentication, credential transactions and leases are real.
These cases do not qualify MCP/native adapters or a provider.
"""

import hashlib
import json
import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
from jsonschema import Draft202012Validator, FormatChecker
import pytest

from nexus_connector_core import R4_PREVIEW_REVISION
from okto_nexus.application.execution_capabilities import ExecutionCapabilityService
from okto_nexus.application.execution_leases import ExecutionLeaseService
from okto_nexus.errors import OktoNexusError
from test_open_bootstrap import opening, begin


def issue(state, *, actor='subject', request_id='cap-request', **changes):
    _, app, _, _, _, _, resolution, _ = state
    body = dict(capability_request_id=request_id, binding_id='binding',
                audience='nexus-mcp-session', actions=['tools/call']) | changes
    return TestClient(app, base_url='https://127.0.0.1:8202').post(
        f"/v1/runtime/sessions/{resolution['session_id']}/capability", json=body,
        headers={'Authorization': 'Bearer ' + app.state.test_agent_keys[actor]})


def service(state):
    return ExecutionCapabilityService(factory=state[0].connection_factory, access=state[2])


def use(state, issued, **changes):
    return service(state).authorize_call(**(dict(token=issued['capability'],
        audience=issued['audience'], action='tools/call', expected_scope=issued['scope']) | changes))


def apply_lease(state, *, serial=0, purpose='initial', request_id='initial'):
    deps, app, access, _, grant, channel, resolution, _ = state
    leases = ExecutionLeaseService(factory=deps.connection_factory, access=access,
                                  fresh_publications=app.state.inventory_fresh_publications)
    request = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION,
        type='lease.renew', request_id=request_id, grant_id=grant['grant_id'],
        expected_lease_serial=serial, purpose=purpose, scope=resolution['scope'],
        connection_id=channel.connection_id, connection_generation=channel.connection_generation)
    granted = leases.issue(request, channel=channel)
    ack = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='lease.applied',
        request_id=request_id, grant_id=grant['grant_id'], lease_id=granted['lease_id'],
        lease_serial=granted['lease_serial'], scope=resolution['scope'],
        connection_id=channel.connection_id, connection_generation=channel.connection_generation,
        application_stage='INSTALLED' if serial == 0 else 'RENEWED')
    return leases, request, granted, ack


def test_capability_public_issue_returns_secret_once_and_replaces_only_before_dispatch(opening):
    response = issue(opening)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    issued = response.json()
    assert issued['scope'] == opening[6]['scope']
    assert issued['audience'] == 'nexus-mcp-session'
    assert issued['mcp_url'] == 'https://127.0.0.1:8202/mcp'
    assert 1 <= issued['expires_in'] <= 120
    assert issued['capability'].startswith('nxc4_')
    schema = json.loads((Path(__file__).parents[2] / 'plans/contratos/http-target.schema.json').read_text())
    Draft202012Validator(dict(schema, **{'$ref': '#/$defs/CapabilityIssue'}),
                         format_checker=FormatChecker()).validate(issued)
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        row = dict(uow.connection.execute('SELECT * FROM execution_session_capabilities').fetchone())
        assert row['secret_hash'] == hashlib.sha256(issued['capability'].encode()).hexdigest()
        assert issued['capability'] not in json.dumps(row)
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 0
    with pytest.raises(OktoNexusError, match='active session'):
        use(opening, issued)
    replay = issue(opening)
    assert replay.status_code == 409, replay.text
    assert replay.json()['error']['code'] == 'CREDENTIAL_MATERIAL_UNAVAILABLE'
    assert replay.json()['error']['capability_id'] == issued['capability_id']
    assert replay.json()['error']['recovery_allowed'] is True
    Draft202012Validator(dict(schema, **{'$ref': '#/$defs/ErrorResponse'})).validate(replay.json())
    conflict = issue(opening, actions=['tools/list'])
    assert conflict.status_code == 409
    assert issue(opening, request_id='other').status_code == 409
    replaced = issue(opening, request_id='replacement', replaces_capability_id=issued['capability_id'])
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()['capability'] != issued['capability']
    with pytest.raises(OktoNexusError):
        use(opening, issued)
    begin(opening)
    refused = issue(opening, request_id='unsafe', replaces_capability_id=replaced.json()['capability_id'])
    assert refused.status_code == 409, refused.text
    assert issue(opening, request_id='replacement', replaces_capability_id=issued['capability_id']).json()['error']['recovery_allowed'] is False


def test_connector_requests_canonical_capability_over_public_http(opening):
    from okto_nexus_connector.transport.https_client import NexusHTTPClient
    from okto_nexus_connector.errors import ConnectorError
    sent = begin(opening)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=opening[1])) as raw:
            async with NexusHTTPClient('https://127.0.0.1:8202', client=raw) as client:
                issued = await client.request_r4_session_capability(opening[1].state.test_agent_keys['subject'],
                    frame=sent.frame, capability_request_id='connector-request',
                    audience='nexus-mcp-session', actions=('tools/call',))
                assert issued.scope == opening[6]['scope']
                assert issued.capability not in repr(issued)
                with pytest.raises(ConnectorError) as replay:
                    await client.request_r4_session_capability(opening[1].state.test_agent_keys['subject'],
                        frame=sent.frame, capability_request_id='connector-request',
                        audience='nexus-mcp-session', actions=('tools/call',))
                assert replay.value.code == 'CREDENTIAL_MATERIAL_UNAVAILABLE'
                assert replay.value.capability_id == issued.capability_id
                assert replay.value.recovery_allowed is False
    asyncio.run(run())


@pytest.mark.parametrize('actor,status', [('operator', 200), ('registrar', 404), ('other', 404)])
def test_capability_issuer_must_own_session_or_be_canonical_operator(opening, actor, status):
    response = issue(opening, actor=actor)
    assert response.status_code == status, response.text


@pytest.mark.parametrize('change', [
    {'audience': 'nexus-executor-control'}, {'actions': ['tools/call', 'tools/call']},
    {'actions': ['']}, {'actions': ['tools/call'] * 129}, {'environment': {}},
    {'capability_request_id': 7}, {'replaces_capability_id': ''},
])
def test_capability_request_rejects_invalid_fields_before_issuance(opening, change):
    response = issue(opening, **change)
    assert response.status_code == 422, response.text
    schema = json.loads((Path(__file__).parents[2] / 'plans/contratos/http-target.schema.json').read_text())
    Draft202012Validator(dict(schema, **{'$ref': '#/$defs/ErrorResponse'})).validate(response.json())
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_session_capabilities').fetchone()[0] == 0


@pytest.mark.parametrize('sql', [
    "UPDATE runtime_profiles SET enabled=0",
    "UPDATE agents SET is_active=0 WHERE agent_id='subject'",
    "UPDATE runtime_execution_grants SET revoked_at='2026-01-01T00:00:00Z'",
    "UPDATE execution_sessions SET owner_generation=owner_generation+1",
    "UPDATE execution_sessions SET lifecycle_state='STOPPED'",
    "UPDATE execution_realizations SET revision=revision+1",
])
def test_capability_revalidates_authority_and_never_returns_old_material(opening, sql):
    issued = issue(opening).json()
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute(sql)
    response = issue(opening, request_id='changed')
    assert response.status_code in (401, 403, 409), response.text
    with pytest.raises(OktoNexusError):
        use(opening, issued)


def test_capability_audiences_do_not_interchange_or_authenticate_as_agent_keys(opening):
    mcp = issue(opening).json()
    response = issue(opening, request_id='native', audience='nexus-native-session', actions=['context'])
    assert response.status_code == 200, response.text
    native = response.json()
    assert native['mcp_url'] is None and native['capability_ref'].startswith('native-cap:')
    assert native['capability'] != mcp['capability']
    with pytest.raises(OktoNexusError):
        use(opening, mcp, audience='nexus-native-session')
    client = TestClient(opening[1])
    assert client.get('/v1/connections/me', headers={'Authorization': 'Bearer ' + mcp['capability']}).status_code == 401


def test_capability_stable_secret_follows_applied_lease_and_keeps_scope_ceiling(opening):
    issued = issue(opening).json()
    begin(opening)
    leases, request, granted, ack = apply_lease(opening)
    with pytest.raises(OktoNexusError):
        use(opening, issued)
    leases.applied(ack, channel=opening[5])
    # Isolate the capability authority gate; provider/open receipt integration
    # is covered by the public runtime journey, not this state transition.
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY'")
        expiry = uow.connection.execute('SELECT valid_until_server FROM execution_session_capabilities').fetchone()[0]
        assert expiry == uow.connection.execute('SELECT valid_until_server FROM execution_leases').fetchone()[0]
    assert use(opening, issued)['capability_id'] == issued['capability_id']
    with pytest.raises(OktoNexusError):
        use(opening, issued, action='tools/list')
    with pytest.raises(OktoNexusError):
        use(opening, issued, expected_scope=issued['scope'] | {'workspace_id': 'other'})
    with pytest.raises(OktoNexusError):
        use(opening, issued, expected_scope=issued['scope'] | {'credential_epoch': True})
    leases, request, granted, ack = apply_lease(opening, serial=1, purpose='renew', request_id='renew')
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT valid_until_server FROM execution_session_capabilities').fetchone()[0] == expiry
    leases.applied(ack, channel=opening[5])
    assert use(opening, issued)['capability_id'] == issued['capability_id']
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_session_capabilities SET valid_until_server='2000-01-01T00:00:00Z'")
    with pytest.raises(OktoNexusError):
        use(opening, issued)


@pytest.mark.parametrize('sql', [
    "UPDATE runtime_execution_grants SET revoked_at='2026-01-01T00:00:00Z'",
    "UPDATE runtime_execution_grants SET revision=revision+1",
    "UPDATE runtime_profiles SET enabled=0",
    "UPDATE agents SET api_key_hash='rotated' WHERE agent_id='subject'",
    "UPDATE execution_agent_revisions SET credential_epoch=credential_epoch+1 WHERE agent_id='subject'",
    "UPDATE execution_agent_revisions SET authorization_revision=authorization_revision+1 WHERE agent_id='subject'",
    "UPDATE execution_agent_revisions SET configuration_revision=configuration_revision+1 WHERE agent_id='subject'",
    "UPDATE execution_sessions SET owner_generation=owner_generation+1",
    "UPDATE execution_leases SET valid_until_server='2000-01-01T00:00:00Z'",
    "UPDATE execution_sessions SET lifecycle_state='STOPPED'",
])
def test_active_capability_immediately_loses_changed_authority(opening, sql):
    issued = issue(opening).json()
    begin(opening)
    leases, _, _, ack = apply_lease(opening)
    leases.applied(ack, channel=opening[5])
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY'")
    assert use(opening, issued)['capability_id'] == issued['capability_id']
    with opening[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute(sql)
    with pytest.raises(OktoNexusError):
        use(opening, issued)
