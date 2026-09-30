"""Real loopback WSS ownership with installed-compatible Connector/Core APIs.

The native peer and readiness qualification are synthetic. This exercises the
Server and daemon-owned execution consumers, including automatic persisted lane
and credential composition. Nonempty reconciliation and rotation remain pending.
"""

import asyncio
import socket

import httpx
import pytest
import uvicorn
from nexus_connector_core import (
    InstallationCandidate, R4_PREVIEW_REVISION,
)
from nexus_connector_core.discovery import fingerprint

from okto_nexus.adapters.inbound.http import executor_link, runtime_v1
from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from okto_nexus.domain.base import iso_plus
from test_binding_operator import onboarding, prepare_delegated, decide_binding
from test_vertical_inventory import _NativeFactory


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
@pytest.mark.parametrize('automatic', [False, True])
def test_owned_connector_reader_dispatches_five_actions_over_real_websocket(onboarding, tmp_path, monkeypatch, automatic):
    from okto_nexus_connector.transport.https_client import NexusHTTPClient, R4BindingView
    from okto_nexus_connector.transport.wss_r4 import connect_r4_connection
    from okto_nexus_connector.services.execution_selection import acknowledge_execution_binding
    from okto_nexus_connector.daemon.app import DaemonApp
    from okto_nexus_connector.errors import ConnectorError
    from okto_nexus_connector.services.r4_execution import R4LaunchSetup
    from okto_nexus_connector.platform.paths import state_dir, state_file
    from okto_nexus_connector.storage.state_store import StateStore, IdentityRecord, ServerProfileRecord, ExecutionExecutorRecord

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
    if not automatic:
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
    from okto_nexus.adapters.inbound.http import connections_v1
    monkeypatch.setattr(connections_v1, 'protocol_info', lambda: qualified)

    async def run():
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        sock.listen()
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(client.app, lifespan='off', log_level='error'))
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        daemon_root = state_dir(tmp_path / 'connector-runtime')
        state = store.load()
        state.preferences['vault.fallback_file.approved'] = True
        StateStore(state_file(daemon_root)).save(state)
        monkeypatch.setenv('OKTO_NEXUS_CONNECTOR_VAULT', 'file')
        daemon = DaemonApp(daemon_root)
        if automatic:
            key = headers['subject']['Authorization'].removeprefix('Bearer ')
            handle = daemon.vault.store('subject', key)
            daemon.vault.store('provider-demo', 'provider-test-secret')
            base_url = f'http://127.0.0.1:{port}'
            def registered_state(state):
                state.connector_id = 'connector'
                state.servers[server_id] = ServerProfileRecord(server_id, base_url, base_url, 'now')
                state.identities.append(IdentityRecord('subject', server_id, 'subject', handle,
                                                       revisions.credential_epoch, 'now'))
                state.execution_executors.append(ExecutionExecutorRecord(server_id, 'connector', 'subject',
                    'register', 'Remote host', executor_id=executor_id, state='REGISTERED',
                    inventory_publication_sequence=1))
            daemon.store.update(registered_state)
        binary = tmp_path / 'remote-only' / 'codex.exe'
        candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
        class CountedFactory(_NativeFactory):
            opens = 0
            async def open(self, prepared, session_id, context, *, stream_epoch):
                assert prepared.cwd == str(tmp_path / 'remote-workspace')
                assert context.r4_authority is not None
                self.opens += 1
                return await super().open(prepared, session_id, context, stream_epoch=stream_epoch)
        native = CountedFactory()
        async def environment(_):
            return {}
        async def candidates(_):
            return [candidate]
        async def launch(_):
            return R4LaunchSetup(environment)
        owner = execution = None
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
            operations.append(resolution['operation_id'])
            async with asyncio.timeout(8):
                while True:
                    if execution.failure is not None:
                        raise execution.failure
                    observed = client.get('/v1/runtime/operations/' + resolution['operation_id'],
                                          headers=headers['subject'])
                    assert observed.status_code == 200, observed.text
                    if observed.json()['receipt_revision'] > 0:
                        receipt = observed.json()
                        assert receipt['operation_id'] == resolution['operation_id']
                        assert receipt['intent_hash'] == resolution['intent_hash']
                        assert receipt['error'] is None, receipt
                        assert receipt['executor_stage'] is not None
                        break
                    await asyncio.sleep(0.01)
            return resolution
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    if serving.done():
                        await serving
                    await asyncio.sleep(0.01)
            from contextlib import AsyncExitStack
            async with AsyncExitStack() as stack:
                if automatic:
                    from functools import partial
                    from okto_nexus_connector.daemon import r4_control, r4_execution
                    async def discover():
                        return [candidate]
                    monkeypatch.setattr(r4_control, 'R4DaemonControl',
                        partial(r4_control.R4DaemonControl, discover=discover))
                    monkeypatch.setattr(r4_execution, 'R4DaemonExecution',
                        partial(r4_execution.R4DaemonExecution, native_factory=native))
                    daemon._start_transports()
                    control = daemon.r4_controls[server_id]
                    async with asyncio.timeout(10):
                        while not control.status()['execution_ready']:
                            if control.error_code:
                                raise AssertionError(control.status())
                            await asyncio.sleep(.01)
                    owner = control.connection
                    execution = control.execution.owner
                else:
                    owner = await asyncio.wait_for(connect_r4_connection(
                        f'ws://127.0.0.1:{port}/v1/runtime/executors/{executor_id}/link',
                        registered.json()['bootstrap_ticket']['ticket'], server_id=server_id, executor_id=executor_id,
                        management_revision=info['management_revision'], snapshot_format=info['executor_snapshot_format'],
                        boot_id='connector-process-boot', report_reconciliation=report), 5)
                    await owner.attach_binding(binding_id=binding['binding_id'], agent_id='subject', ticket=ticket,
                        credential_epoch=revisions.credential_epoch, authorization_revision=revisions.authorization,
                        configuration_revision=revisions.configuration)
                    raw = await stack.enter_async_context(httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app)))
                    http = await stack.enter_async_context(NexusHTTPClient('https://127.0.0.1:8202', client=raw))
                    async def publish(frame):
                        await http.publish_operation_receipt(ticket, frame=frame)
                    execution = daemon.own_r4_connection(owner, candidate_provider=candidates,
                        launch_provider=launch, publish_receipt=publish, native_factory=native)
                    with pytest.raises(ConnectorError) as duplicate:
                        daemon.own_r4_connection(owner, candidate_provider=candidates,
                            launch_provider=launch, publish_receipt=publish, native_factory=native)
                    assert duplicate.value.code == 'OPERATION_CONFLICT'
                opened = await admit('runtime.start', new_session=True)
                session_id = opened['scope']['session_id']
                await admit('turn.submit', session_id=session_id, text='Hello')
                await admit('turn.steer', session_id=session_id, text='Continue carefully.',
                    target={'kind': 'native_turn_id', 'expected_turn_id': 'turn-from-native'})
                await admit('turn.interrupt', session_id=session_id,
                    target={'kind': 'current_run', 'expected_turn_id': None})
                await admit('runtime.close', session_id=session_id)
                async with asyncio.timeout(5):
                    while execution.pending_count:
                        await asyncio.sleep(0)
            assert owner.online and owner.usage == {False: (0, 0), True: (0, 0)}
            assert native.native.stopped
            assert native.opens == 1
            assert [kind for kind, _ in native.native.sent] == ['send_turn', 'steer', 'interrupt']
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 5
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_dispatch_outbox WHERE attempt_no<>1').fetchone()[0] == 0
                assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()) == ('CLOSED', 'CLOSED')
        finally:
            try:
                result = await daemon._shutdown()
                if owner is not None:
                    await owner.close()
                assert result == 0
            finally:
                server.should_exit = True
                await asyncio.wait_for(serving, 5)
                sock.close()
    asyncio.run(run())
