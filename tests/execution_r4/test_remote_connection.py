"""Real loopback WSS ownership with installed-compatible Connector/Core APIs.

The native peer and readiness qualification are synthetic. This exercises the
Server and Connector connection owner, not the still-pending daemon composition.
"""

import asyncio
import socket

import httpx
import pytest
import uvicorn
from nexus_connector_core import (
    CoreError, ControlOperation, InstallationCandidate, LaunchIntent, OpenOperation,
    R4_PREVIEW_REVISION, TurnOperation, r4_close_operation,
)
from nexus_connector_core.discovery import fingerprint

from okto_nexus.adapters.inbound.http import executor_link, runtime_v1
from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from okto_nexus.domain.base import iso_plus
from test_binding_operator import onboarding, prepare_delegated, decide_binding
from test_vertical_inventory import _NativeFactory


@pytest.mark.parametrize('onboarding', ['connector-realization'], indirect=True)
def test_owned_connector_reader_dispatches_five_actions_over_real_websocket(onboarding, tmp_path, monkeypatch):
    from okto_nexus_connector.transport.https_client import NexusHTTPClient, R4BindingView
    from okto_nexus_connector.transport.wss_r4 import connect_r4_connection, apply_r4_lease
    from okto_nexus_connector.services.execution_selection import acknowledge_execution_binding
    from okto_nexus_connector.services.core_host import CoreRuntimeHost
    from okto_nexus_connector.platform.paths import state_dir
    from okto_nexus_connector.storage.state_store import StateStore

    deps, client, headers, prepare = onboarding
    _, apply, approval_id = prepare_delegated(client, headers, prepare)
    assert decide_binding(client, headers, approval_id).status_code == 200
    response = client.post('/v1/connections/bindings:apply', json=apply, headers=headers['subject'])
    assert response.status_code == 200, response.text
    binding = response.json()
    store = StateStore(tmp_path / 'connector-state.json')
    acknowledge_execution_binding(store, binding=R4BindingView(**binding))
    server_id, executor_id = binding['server_id'], binding['executor_id']
    granted = client.post('/api/v1/harness/grants', headers=headers['operator'], json={
        'actor_agent_id': 'subject', 'endpoint_id': binding['endpoint_id'],
        'actions': ['open', 'send', 'steer', 'interrupt', 'close'], 'max_executions': 2,
        'expires_at': iso_plus(deps.clock.now_iso(), 600)})
    assert granted.status_code == 200, granted.text
    registered = client.post('/v1/connections/executors:register', headers=headers['subject'], json={
        'client_intent_id': 'register', 'connector_id': 'connector', 'label': 'Remote host', 'control_capabilities': []})
    assert registered.status_code == 200, registered.text
    ticketed = client.post(f"/v1/connections/bindings/{binding['binding_id']}/ticket",
        headers=headers['subject'], json={'client_intent_id': 'mux-lane', 'credential_request_id': 'mux-key',
            'audience': 'nexus-executor-control', 'scopes': ['lane:attach', 'lease:request', 'receipt:publish']})
    assert ticketed.status_code == 200, ticketed.text
    ticket = ticketed.json()['ticket']
    _, revisions, _ = current_agent_revisions(deps.connection_factory, agent_id='subject')
    info = executor_link.protocol_info()
    qualified = {**info, 'remote_execution_ready': True, 'nxl_accepted': [R4_PREVIEW_REVISION]}
    monkeypatch.setattr(executor_link, 'protocol_info', lambda: qualified)
    monkeypatch.setattr(runtime_v1, 'protocol_info', lambda: qualified)

    async def run():
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        sock.listen()
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(client.app, lifespan='off', log_level='error'))
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        host = CoreRuntimeHost(state_dir(tmp_path / 'connector-runtime'), None)
        binary = tmp_path / 'remote-only' / 'codex.exe'
        candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
        class CountedFactory(_NativeFactory):
            opens = 0
            async def open(self, *args, **kwargs):
                self.opens += 1
                return await super().open(*args, **kwargs)
        native = CountedFactory()
        async def environment(_):
            return {}
        runtime = None
        owner = None
        operations = []
        async def report(request):
            assert request['operation_ids'] == request['session_ids'] == []
            return {k: request[k] for k in ('protocol_major', 'contract_revision', 'server_id', 'executor_id',
                'connection_id', 'connection_generation', 'reconcile_id', 'cursor')} | dict(
                    type='reconcile.report', next_cursor=None, complete=True, receipts=[], claims=[],
                    stream_watermarks=[], ownership_facts=[])
        async def admit(intent, **options):
            resolved = client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json={
                'client_intent_id': 'mux-' + intent, 'intent': intent, 'binding_id': binding['binding_id'],
                'workspace_binding_id': binding['workspace_binding_id'], **options})
            assert resolved.status_code == 200, resolved.text
            resolution = resolved.json()
            assert resolution['can_submit'], resolution['blockers']
            admitted = client.post('/v1/runtime/operations', headers=headers['subject'], json={
                k: resolution[k] for k in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')})
            assert admitted.status_code == 202, admitted.text
            item = await asyncio.wait_for(owner.receive_operation(control=intent in {
                'turn.steer', 'turn.interrupt', 'runtime.close'}), 5)
            frame = owner.require_current(item)
            assert frame['operation_id'] == resolution['operation_id']
            assert frame['intent_hash'] == resolution['intent_hash']
            operations.append(frame['operation_id'])
            return item, frame, resolution['scope']
        def context(item):
            return runtime.r4_operation_context(owner.require_current(item),
                connection_id=owner.state.connection_id, connection_generation=owner.state.connection_generation)
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    if serving.done():
                        await serving
                    await asyncio.sleep(0.01)
            owner = await asyncio.wait_for(connect_r4_connection(
                f'ws://127.0.0.1:{port}/v1/runtime/executors/{executor_id}/link',
                registered.json()['bootstrap_ticket']['ticket'], server_id=server_id, executor_id=executor_id,
                management_revision=info['management_revision'], snapshot_format=info['executor_snapshot_format'],
                boot_id='connector-process-boot', report_reconciliation=report), 5)
            await owner.attach_binding(binding_id=binding['binding_id'], agent_id='subject', ticket=ticket,
                credential_epoch=revisions.credential_epoch, authorization_revision=revisions.authorization,
                configuration_revision=revisions.configuration)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app)) as raw:
                async with NexusHTTPClient('https://127.0.0.1:8202', client=raw) as http:
                    item, frame, scope = await admit('runtime.start', new_session=True)
                    runtime = await host.build_r4(store, frame=owner.require_current(item),
                        candidates=[candidate], environment=environment, factory=native)
                    with pytest.raises(CoreError):
                        context(item)
                    assert native.opens == 0
                    await apply_r4_lease(owner, owner.state, runtime, scope=scope, grant_id=frame['grant_id'])
                    ctx = context(item)
                    prepared = await runtime.prepare(LaunchIntent('subject', binding['workspace_id'], candidate.adapter_id), ctx)
                    assert prepared.cwd == str(tmp_path / 'remote-workspace')
                    opened = await runtime.open(OpenOperation(frame['operation_id'], scope['session_id'], 'mux-epoch', prepared), ctx)
                    await http.publish_core_open_receipt(ticket, submit_frame=frame, core_receipt=opened,
                        context=ctx, prepared=prepared, stream_epoch='mux-epoch', receipt_revision=1)
                    owner.release_operation(item)
                    item, frame, _ = await admit('turn.submit', session_id=scope['session_id'], text='Hello')
                    ctx = context(item)
                    receipt = await runtime.submit(TurnOperation(frame['operation_id'], scope['session_id'], frame['payload']['text']), ctx)
                    await http.publish_core_turn_receipt(ticket, submit_frame=frame, core_receipt=receipt, context=ctx, receipt_revision=1)
                    owner.release_operation(item)
                    for action, target in [('steer', {'kind': 'native_turn_id', 'expected_turn_id': 'turn-from-native'}),
                                           ('interrupt', {'kind': 'current_run', 'expected_turn_id': None})]:
                        options = {'text': 'Continue carefully.'} if action == 'steer' else {}
                        item, frame, _ = await admit('turn.' + action, session_id=scope['session_id'], target=target, **options)
                        ctx = context(item)
                        receipt = await runtime.control(ControlOperation(frame['operation_id'], scope['session_id'], action,
                            text=frame['payload'].get('text'), reason=frame['payload'].get('reason'),
                            expected_turn_id=frame.get('expected_turn_id')), ctx)
                        await getattr(http, 'publish_core_' + action + '_receipt')(ticket, submit_frame=frame,
                            core_receipt=receipt, context=ctx, receipt_revision=1)
                        owner.release_operation(item)
                    item, frame, _ = await admit('runtime.close', session_id=scope['session_id'])
                    ctx = context(item)
                    receipt = await runtime.close(r4_close_operation(frame), ctx)
                    await http.publish_core_close_receipt(ticket, submit_frame=frame, core_receipt=receipt, context=ctx, receipt_revision=1)
                    owner.release_operation(item)
            assert owner.online and owner.usage == {False: (0, 0), True: (0, 0)}
            assert native.native.stopped
            assert native.opens == 1
            assert [kind for kind, _ in native.native.sent] == ['send_turn', 'steer', 'interrupt']
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 5
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_dispatch_outbox WHERE attempt_no<>1').fetchone()[0] == 0
                assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()) == ('CLOSED', 'CLOSED')
        finally:
            if owner is not None:
                await owner.close()
            await host.shutdown_all()
            server.should_exit = True
            await asyncio.wait_for(serving, 5)
            sock.close()
    asyncio.run(run())
