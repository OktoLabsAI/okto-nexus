"""Public onboarding/admission through Core open with a synthetic native peer.

Only identities are seeded. The dispatcher is invoked explicitly and the
qualification gate is synthetic: this does not qualify a daemon or provider.
"""

import asyncio

import httpx
import pytest
from nexus_connector_core import (
    CoreError, InstallationCandidate, LaunchIntent, OpenOperation,
    R4_PREVIEW_REVISION, ShutdownPolicy, TurnOperation, create_runtime,
    decode_r4_frame, encode_r4_frame,
)
from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.journal import open_journal

from okto_nexus.adapters.inbound.http import executor_link, runtime_v1
from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from okto_nexus.application.execution_dispatch import (
    AuthorizedOpenBootstrap, begin_execution_send, reserve_execution_dispatch,
)
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.base import iso_plus

from test_binding_operator import onboarding, prepare_delegated, decide_binding
from test_ns09 import negotiate
from test_vertical_inventory import _NativeFactory


def test_public_binding_grant_admission_bootstrap_core_and_receipts(onboarding, tmp_path, monkeypatch):
    from okto_nexus_connector.transport.https_client import NexusHTTPClient
    from okto_nexus_connector.transport.wss_r4 import R4ControlState, apply_r4_lease

    deps, client, headers, prepare = onboarding
    app = client.app
    proposal, apply, approval_id = prepare_delegated(client, headers, prepare)
    assert decide_binding(client, headers, approval_id).status_code == 200
    applied = client.post('/v1/connections/bindings:apply', json=apply, headers=headers['subject'])
    assert applied.status_code == 200, applied.text
    binding = applied.json()
    server, executor = binding['server_id'], binding['executor_id']
    issued = client.post('/api/v1/harness/grants', headers=headers['operator'], json={
        'actor_agent_id': 'subject', 'endpoint_id': binding['endpoint_id'],
        'actions': ['open', 'send', 'close'], 'max_executions': 2,
        'expires_at': iso_plus(deps.clock.now_iso(), 600)})
    assert issued.status_code == 200, issued.text
    canonical = issued.json()['data']
    # Refresh bootstrap credentials through the same public registration.
    registered = client.post('/v1/connections/executors:register', headers=headers['subject'], json={
        'client_intent_id': 'register', 'connector_id': 'connector',
        'label': 'Remote host', 'control_capabilities': []})
    assert registered.status_code == 200, registered.text
    assert registered.json()['executor_id'] == executor
    link = registered.json()['bootstrap_ticket']['ticket']
    issued_ticket = client.post(f"/v1/connections/bindings/{binding['binding_id']}/ticket",
        headers=headers['subject'], json={'client_intent_id': 'lane', 'credential_request_id': 'lane-key',
            'audience': 'nexus-executor-control', 'scopes': ['lane:attach', 'lease:request', 'receipt:publish']})
    assert issued_ticket.status_code == 200, issued_ticket.text
    lane = issued_ticket.json()['ticket']
    _, revisions, _ = current_agent_revisions(deps.connection_factory, agent_id='subject')
    info = executor_link.protocol_info()
    qualified = {**info, 'remote_execution_ready': True, 'nxl_accepted': [R4_PREVIEW_REVISION]}
    monkeypatch.setattr(executor_link, 'protocol_info', lambda: qualified)
    monkeypatch.setattr(runtime_v1, 'protocol_info', lambda: qualified)
    access = build_execution_access(deps)

    def admit_public(intent_id, intent, **options):
        resolved = client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json={
            'client_intent_id': intent_id, 'intent': intent, 'binding_id': binding['binding_id'],
            'workspace_binding_id': binding['workspace_binding_id'], **options})
        assert resolved.status_code == 200, resolved.text
        resolution = resolved.json()
        assert resolution['can_submit'], resolution['blockers']
        request = {k: resolution[k] for k in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')}
        submitted = client.post('/v1/runtime/operations', headers=headers['subject'], json=request)
        assert submitted.status_code == 202, submitted.text
        replay = client.post('/v1/runtime/operations', headers=headers['subject'], json=request)
        assert replay.status_code == 200 and replay.json() == submitted.json()
        reservation = reserve_execution_dispatch(deps.connection_factory, server_id=server,
                                                  executor_id=executor, remote_ready=True)
        assert reservation.operation_id == resolution['operation_id']
        return resolution, begin_execution_send(deps.connection_factory, reservation=reservation,
            remote_ready=True, fresh_publications=app.state.inventory_fresh_publications, access=access)

    with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
            headers={'Authorization': f'Bearer {link}'}, subprotocols=['nxl.v1']) as ws:
        channel = negotiate(ws, info, revisions, lane, server, executor, binding_id=binding['binding_id'])
        resolution, sent = admit_public('open-public', 'runtime.start', new_session=True)
        assert isinstance(sent, AuthorizedOpenBootstrap)
        assert sent.grant_id == canonical['grant_id']

        class Peer:
            request = None
            async def send(self, raw):
                frame = decode_r4_frame(raw.encode())
                if frame['type'] == 'lease.renew':
                    self.request = frame
                await asyncio.to_thread(ws.send_text, raw)
            async def recv(self):
                return await asyncio.to_thread(ws.receive_text)

        class CountedFactory(_NativeFactory):
            opens = 0
            async def open(self, *args, **kwargs):
                self.opens += 1
                return await super().open(*args, **kwargs)

        async def run():
            journal = await open_journal(tmp_path / 'public-core.db')
            native = CountedFactory()
            binary = tmp_path / 'remote-only' / 'codex.exe'
            candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
            async def environment(_):
                return {}
            runtime = create_runtime(journal=journal, environment=environment,
                candidates={candidate.adapter_id: candidate}, workspace_roots={binding['workspace_id']: str(tmp_path)},
                native_factory=native)
            peer = Peer()
            state = R4ControlState(server, executor, channel.connection_id, channel.connection_generation, True)
            try:
                with pytest.raises(CoreError):
                    runtime.r4_operation_context(sent.frame, connection_id=channel.connection_id,
                                                 connection_generation=channel.connection_generation)
                assert native.opens == 0
                await apply_r4_lease(peer, state, runtime, scope=sent.scope, grant_id=sent.grant_id)
                # Order a query after the ACK on the same reader-owned socket.
                await peer.send(encode_r4_frame(peer.request).decode())
                assert decode_r4_frame((await peer.recv()).encode())['lease_serial'] == 1
                context = runtime.r4_operation_context(sent.frame, connection_id=channel.connection_id,
                                                       connection_generation=channel.connection_generation)
                prepared = await runtime.prepare(LaunchIntent('subject', binding['workspace_id'], candidate.adapter_id), context)
                operation = OpenOperation(resolution['operation_id'], sent.scope['session_id'], 'public-epoch', prepared)
                opened = await runtime.open(operation, context)
                assert (await runtime.open(operation, context)).operation_id == opened.operation_id
                assert native.opens == 1
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as raw:
                    async with NexusHTTPClient('https://127.0.0.1:8202', client=raw) as http:
                        await http.publish_core_open_receipt(lane, submit_frame=sent.frame, core_receipt=opened,
                            context=context, prepared=prepared, stream_epoch='public-epoch', receipt_revision=1)
                        turn, dispatched = admit_public('turn-public', 'turn.submit', session_id=sent.scope['session_id'], text='Hello')
                        turn_context = runtime.r4_operation_context(dispatched.frame, connection_id=channel.connection_id,
                                                                   connection_generation=channel.connection_generation)
                        receipt = await runtime.submit(TurnOperation(turn['operation_id'], sent.scope['session_id'], 'Hello'), turn_context)
                        await http.publish_core_turn_receipt(lane, submit_frame=dispatched.frame,
                            core_receipt=receipt, context=turn_context, receipt_revision=1)
                assert native.native.sent == [('send_turn', turn['operation_id'])]
                observed = client.get(f"/v1/runtime/operations/{turn['operation_id']}", headers=headers['subject'])
                assert observed.status_code == 200 and observed.json()['executor_stage'] == receipt.stage
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    conn = uow.connection
                    assert conn.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 2
                    assert conn.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0] == 1
                    assert conn.execute('SELECT used_executions FROM runtime_execution_grants').fetchone()[0] == 1
                assert reserve_execution_dispatch(deps.connection_factory, server_id=server,
                                                  executor_id=executor, remote_ready=True) is None
            finally:
                await runtime.shutdown(ShutdownPolicy(0, 0))
                await journal.aclose()
        asyncio.run(run())
