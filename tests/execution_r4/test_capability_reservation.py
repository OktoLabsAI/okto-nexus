"""Connector durable issuance against canonical Nexus credential transactions."""

import asyncio
import json

import httpx
import pytest

from test_session_capabilities import opening, begin


@pytest.mark.parametrize('lost_response', [False, True])
def test_connector_persists_issuance_and_never_replaces_dispatched_secret(opening, tmp_path, lost_response):
    from okto_nexus_connector.errors import CapabilityMaterialUnavailable, ConnectorError
    from okto_nexus_connector.identity.vault import RestrictedFileVault
    from okto_nexus_connector.services.session_capabilities import SessionCapabilityOwner
    from okto_nexus_connector.storage.state_store import StateStore
    from okto_nexus_connector.transport.https_client import NexusHTTPClient

    sent = begin(opening)
    store = StateStore(tmp_path / 'connector-state.json')
    vault = RestrictedFileVault(tmp_path, approved=True)
    requests = []

    class Transport(httpx.ASGITransport):
        async def handle_async_request(self, request):
            body = json.loads(request.content)
            persisted = StateStore(store.path).load().session_capabilities[0]
            assert body['capability_request_id'] == persisted.request_id
            assert persisted.status == 'REQUESTED'
            requests.append(body)
            response = await super().handle_async_request(request)
            if lost_response and len(requests) == 1:
                assert response.status_code == 200
                await response.aclose()
                raise httpx.ReadTimeout('Response lost after credential commit.', request=request)
            return response

    async def run():
        async with httpx.AsyncClient(transport=Transport(app=opening[1])) as raw:
            async with NexusHTTPClient('https://127.0.0.1:8202', client=raw) as http:
                args = dict(frame=sent.frame, audience='nexus-native-session',
                    actions=('handoff.get', 'handoff.claim', 'handoff.complete'), require_current=lambda: None)
                key = opening[1].state.test_agent_keys['subject']
                owner = SessionCapabilityOwner(store, vault)
                if lost_response:
                    with pytest.raises(ConnectorError) as uncertain:
                        await owner.reserve(http, key, **args)
                    assert uncertain.value.possible_effect and not uncertain.value.retry_safe
                else:
                    issued = await owner.reserve(http, key, **args)
                    record = store.load().session_capabilities[0]
                    assert vault.resolve(record.secret_handle) == issued.capability
                    assert issued.capability not in store.path.read_text()
                    assert record.status == 'STORED'
                await owner.close()
                restarted = SessionCapabilityOwner(StateStore(store.path), vault)
                with pytest.raises(CapabilityMaterialUnavailable) as unavailable:
                    await restarted.reserve(http, key, **args)
                assert not unavailable.value.recovery_allowed
                await restarted.close()
    asyncio.run(run())
    assert len(requests) == (2 if lost_response else 1)
    assert len({r['capability_request_id'] for r in requests}) == 1
    assert all(r['replaces_capability_id'] is None for r in requests)
    with opening[0].connection_factory.unit_of_work(write=False) as uow:
        records = uow.connection.execute('SELECT capability_id,revoked_at FROM execution_session_capabilities').fetchall()
        assert len(records) == 1 and records[0]['revoked_at'] is None
        assert records[0]['capability_id'] == store.load().session_capabilities[0].capability_id
