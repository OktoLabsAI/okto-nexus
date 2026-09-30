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
@pytest.mark.parametrize('automatic,publication_failure,reconcile_closed,history_count', [
    (False, None, False, 0), (True, None, False, 0), (False, 'before_commit', False, 0),
    (False, 'lost_ack', False, 0), (False, 'core_commit', False, 0),
    (False, None, True, 0), (False, 'core_commit', True, 0), (False, None, True, 260)])
def test_owned_connector_reader_dispatches_five_actions_over_real_websocket(onboarding, tmp_path, monkeypatch, automatic, publication_failure, reconcile_closed, history_count):
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
        if automatic or publication_failure:
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
                self.context = context
                return await super().open(prepared, session_id, context, stream_epoch=stream_epoch)
        native = CountedFactory()
        async def environment(_):
            return {}
        async def candidates(_):
            return [candidate]
        async def launch(_):
            return R4LaunchSetup(environment)
        owner = execution = None
        recovery_host = None
        dispatched = {}
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
            if publication_failure and intent == 'runtime.close':
                async with asyncio.timeout(8):
                    while execution.failure is None or execution.pending_count:
                        await asyncio.sleep(.01)
                assert isinstance(execution.failure, OSError)
                return resolution
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
                        if intent == 'runtime.close':
                            assert receipt['executor_stage'] == 'SUCCEEDED'
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
                        if publication_failure == 'before_commit' and frame['operation_id'] == operations[-1] and frame['stage'] == 'SUCCEEDED':
                            raise OSError('The receipt request was not delivered.')
                        await http.publish_operation_receipt(ticket, frame=frame)
                        if publication_failure == 'lost_ack' and frame['stage'] == 'SUCCEEDED':
                            raise OSError('The receipt acknowledgment was lost.')
                    execution = daemon.own_r4_connection(owner, candidate_provider=candidates,
                        launch_provider=launch, publish_receipt=publish, native_factory=native)
                    with pytest.raises(ConnectorError) as duplicate:
                        daemon.own_r4_connection(owner, candidate_provider=candidates,
                            launch_provider=launch, publish_receipt=publish, native_factory=native)
                    assert duplicate.value.code == 'OPERATION_CONFLICT'
                execute = execution._execute
                async def capture(item):
                    dispatched[item.frame['action']] = item.frame
                    return await execute(item)
                execution._execute = capture
                if publication_failure == 'core_commit':
                    original_record = execution.publications.record
                    def interrupted_record(frame):
                        if frame['stage'] == 'SUCCEEDED':
                            raise OSError('The receipt projection write was interrupted.')
                        original_record(frame)
                    monkeypatch.setattr(execution.publications, 'record', interrupted_record)
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
                if publication_failure:
                    from okto_nexus_connector.storage.r4_publications import R4PublicationStore
                    from okto_nexus_connector.services.r4_publications import recover_publications
                    pending = R4PublicationStore.for_state(daemon.store)
                    saved = pending.ready(server_id, executor_id)
                    if publication_failure == 'core_commit':
                        assert not saved
                        bound = pending.unprojected(server_id, executor_id)
                        assert len(bound) == 1 and bound[0]['source']['connection_id'] == owner.state.connection_id
                    else:
                        assert len(saved) == 1 and saved[0]['stage'] == 'SUCCEEDED'
                        assert saved[0]['connection_id'] == owner.state.connection_id
                    # Simulate the previous credential's expiry. Recovery cannot
                    # replace a still-bound live ticket and must not bypass it.
                    with deps.connection_factory.unit_of_work() as uow:
                        uow.connection.execute("UPDATE execution_link_tickets SET expires_at='2000-01-01T00:00:00+00:00' "
                            "WHERE binding_id=?", (binding['binding_id'],))
                    async def current():
                        pass
                    async with NexusHTTPClient(base_url) as recovery_http:
                        recovered = await recover_publications(daemon.store, daemon.vault, recovery_http,
                            server_id=server_id, executor_id=executor_id, require_current=current,
                            journal=await daemon.host.ensure_history_journal())
                    assert list(recovered) == [binding['binding_id']]
                    assert not pending.pending(server_id, executor_id)
                    final = client.get('/v1/runtime/operations/' + operations[-1], headers=headers['subject']).json()
                    assert final['executor_stage'] == 'SUCCEEDED' and final['receipt_revision'] == 1
                if reconcile_closed:
                    from okto_nexus_connector.services.r4_reconciliation import R4ReconciliationReporter
                    from okto_nexus_connector.services.core_host import CoreRuntimeHost
                    generation = owner.state.connection_generation
                    await execution.stop()
                    await owner.close()
                    async with asyncio.timeout(5):
                        while True:
                            with deps.connection_factory.unit_of_work(write=False) as uow:
                                state = uow.connection.execute('SELECT control_state FROM execution_executors WHERE executor_id=?',
                                    (executor_id,)).fetchone()[0]
                            if state == 'DISCONNECTED':
                                break
                            await asyncio.sleep(.01)
                    if history_count:
                        # Synthetic historical facts exercise pagination. The
                        # five actual native commands above are not repeated.
                        import hashlib
                        from nexus_connector_core import (OperationKey, OperationReceipt, prepare_r4_receipt_binding,
                            project_r4_bound_receipt, r4_submit_intent_hash)
                        from nexus_connector_core.protocol import canonical_json
                        from okto_nexus_connector.storage.r4_publications import R4PublicationStore
                        journal = await daemon.host.ensure_history_journal()
                        publications = R4PublicationStore.for_state(daemon.store)
                        template = dispatched['turn.submit']
                        with deps.connection_factory.unit_of_work(write=False) as uow:
                            tables = {table: dict(uow.connection.execute('SELECT * FROM ' + table + ' WHERE operation_id=?',
                                (template['operation_id'],)).fetchone()) for table in
                                ('execution_operations','execution_dispatch_outbox','execution_receipts')}
                        prepared_history = []
                        for index in range(history_count):
                            frame = dict(template, operation_id=f'history-{index:04}-' + 'x' * 140)
                            frame['intent_hash'] = r4_submit_intent_hash(frame)
                            association = prepare_r4_receipt_binding(frame, native.context)
                            key = OperationKey(server_id, executor_id, frame['operation_id'])
                            await journal.admit(key, association['core_intent_hash'], session_id)
                            await journal.mark_possible_effect(key)
                            fact = await journal.record_receipt(key, OperationReceipt(key.operation_id,
                                association['core_intent_hash'], 'SUBMITTED', True, False, session_id,
                                native_id=native.native.native_id))
                            projected = project_r4_bound_receipt(association, fact, key=key, receipt_revision=1)
                            await asyncio.to_thread(publications.reserve, frame)
                            await asyncio.to_thread(publications.bind, association)
                            await asyncio.to_thread(publications.record, projected)
                            await asyncio.to_thread(publications.acknowledge, projected)
                            prepared_history.append((frame, projected))
                        with deps.connection_factory.unit_of_work() as uow:
                            for frame, projected in prepared_history:
                                for table, source in tables.items():
                                    values = dict(source, operation_id=frame['operation_id'])
                                    if 'intent_hash' in values:
                                        values['intent_hash'] = frame['intent_hash']
                                    if table == 'execution_receipts':
                                        raw = canonical_json(projected)
                                        values.update(canonical_frame=raw.decode(),
                                                      frame_digest='sha256:' + hashlib.sha256(raw).hexdigest())
                                    if table == 'execution_dispatch_outbox':
                                        values['attempt_token'] = frame['operation_id']
                                    uow.connection.execute('INSERT INTO ' + table + '(' + ','.join(values) + ') VALUES (' +
                                        ','.join('?' for _ in values) + ')', tuple(values.values()))
                    recovery_host = CoreRuntimeHost(daemon.host.root, daemon.vault)
                    reporter = R4ReconciliationReporter(daemon.store, recovery_host, server_id, executor_id)
                    reports = []
                    async def reconciled(request):
                        report = await reporter.report(request)
                        reports.append(report)
                        return report
                    owner = await asyncio.wait_for(connect_r4_connection(
                        f'ws://127.0.0.1:{port}/v1/runtime/executors/{executor_id}/link',
                        registered.json()['bootstrap_ticket']['ticket'], server_id=server_id, executor_id=executor_id,
                        management_revision=info['management_revision'], snapshot_format=info['executor_snapshot_format'],
                        boot_id='recovery-boot', report_reconciliation=reconciled), 10)
                    assert owner.state.control_ready and owner.state.connection_generation > generation
                    assert reports and reports[0]['receipts'] and reports[0]['claims'][0]['state'] == 'RELEASED'
                    assert not reporter.blocked
                    if history_count:
                        from nexus_connector_core import encode_r4_frame
                        assert len(reports) == 2 and len(reports[0]['receipts']) == 256
                        assert sum(len(report['receipts']) for report in reports) == history_count + 4
                        assert len(encode_r4_frame(reports[0])) > 64 * 1024
            assert owner.online is (not bool(publication_failure) or reconcile_closed)
            assert owner.usage == {False: (0, 0), True: (0, 0)}
            assert native.native.stopped
            assert native.opens == 1
            assert [kind for kind, _ in native.native.sent] == ['send_turn', 'steer', 'interrupt']
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 5 + history_count
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts').fetchone()[0] == 5 + history_count
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_dispatch_outbox WHERE attempt_no<>1').fetchone()[0] == 0
                expected_session = ('READY', 'SUPERSEDED') if publication_failure in ('before_commit', 'core_commit') and not reconcile_closed else ('CLOSED', 'CLOSED')
                # Receipt ingress preserves history after disconnect. Adoption
                # of that fact into session readiness remains reconciliation.
                assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()) == expected_session
        finally:
            try:
                if recovery_host is not None:
                    await recovery_host.shutdown_all()
                result = await daemon._shutdown()
                if owner is not None:
                    await owner.close()
                assert result == (1 if publication_failure else 0)
            finally:
                server.should_exit = True
                await asyncio.wait_for(serving, 5)
                sock.close()
    asyncio.run(run())
