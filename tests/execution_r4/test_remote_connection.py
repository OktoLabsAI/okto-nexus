"""Real loopback WSS ownership with installed-compatible Connector/Core APIs.

The native peer and readiness qualification are synthetic. This exercises the
Server and daemon-owned execution consumers, including automatic persisted lane
and credential composition, confirmed closed-session reconciliation and pending event recovery. Full rotation/active-session adoption remain pending.
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
@pytest.mark.parametrize('automatic,publication_failure,reconcile_closed,history_count,event_recovery', [
    (False, None, False, 0, None), (True, None, False, 0, None), (False, 'before_commit', False, 0, None),
    (False, 'lost_ack', False, 0, None), (False, 'core_commit', False, 0, None),
    (False, None, True, 0, None), (False, 'core_commit', True, 0, None), (False, None, True, 260, None),
    (True, None, False, 0, 'unsent'), (True, None, False, 0, 'ack_lost'),
    (True, None, False, 0, 'cold_unsent'), (True, None, False, 0, 'cold_ack_lost'),
    (True, None, False, 0, 'active_disconnect'), (True, None, False, 0, 'lease_renewal')])
def test_owned_connector_reader_dispatches_five_actions_over_real_websocket(onboarding, tmp_path, monkeypatch, automatic, publication_failure, reconcile_closed, history_count, event_recovery, native_decision=None, cli_admission=False, initial_prompt=False, domain_delivery=False, combined_winner=None, reset_active=False, check_presence=False, operator_containment=False, one_shot=False):
    from okto_nexus_connector.transport.https_client import NexusHTTPClient, R4BindingView
    from okto_nexus_connector.transport.wss_r4 import connect_r4_connection
    from okto_nexus_connector.services.execution_selection import acknowledge_execution_binding
    from okto_nexus_connector.daemon.app import DaemonApp
    from okto_nexus_connector.errors import ConnectorError
    from okto_nexus_connector.services.r4_execution import R4LaunchSetup
    from okto_nexus_connector.platform.paths import state_dir, state_file
    from okto_nexus_connector.storage.state_store import StateStore, IdentityRecord, ServerProfileRecord, ExecutionExecutorRecord

    deps, client, headers, prepare = onboarding
    if native_decision is not None:
        deps.config.feature_hitl = True
    _, apply, approval_id = prepare_delegated(client, headers, prepare)
    assert decide_binding(client, headers, approval_id).status_code == 200
    response = client.post('/v1/connections/bindings:apply', json=apply, headers=headers['subject'])
    assert response.status_code == 200, response.text
    binding = response.json()
    store = StateStore(tmp_path / 'connector-state.json')
    server_id, executor_id = binding['server_id'], binding['executor_id']
    granted = client.post('/api/v1/harness/grants', headers=headers['operator'], json={
        'actor_agent_id': 'subject', 'endpoint_id': binding['endpoint_id'],
        'actions': ['open', 'send', 'steer', 'interrupt', 'close'], 'max_executions': 10 if one_shot else 2 + bool(initial_prompt),
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
    qualified = info
    assert info['remote_execution_ready'] is True
    assert info['nxl_accepted'] == [R4_PREVIEW_REVISION]
    assert runtime_v1.protocol_info() == info
    from okto_nexus.adapters.inbound.http import connections_v1
    assert connections_v1.protocol_info() == info
    if combined_winner:
        from test_combined_consumption import prepare_embedded
        embedded = prepare_embedded(onboarding, binding, tmp_path, monkeypatch, qualified)
    if domain_delivery:
        from okto_nexus.bootstrap import execution_compat
        monkeypatch.setattr(execution_compat, 'protocol_info', lambda: qualified)
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='conversation' WHERE endpoint_id=?",
                                   (binding['endpoint_id'],))
            if one_shot:
                from okto_nexus.application.runtime_mcp_presets import save
                uow.connection.execute("UPDATE runtime_policy_defaults SET session_policy='one_shot'")
                save(uow.connection, endpoint_id=binding['endpoint_id'], expected_revision=0,
                     servers=[dict(name='remote-preset', transport='stdio', command='example-mcp', enabled=False)])
            if combined_winner:
                uow.connection.execute('UPDATE agent_endpoints SET priority=? WHERE endpoint_id=?',
                    (20 if combined_winner == 'remote' else 10, binding['endpoint_id']))
                uow.connection.execute('UPDATE agent_endpoints SET priority=? WHERE endpoint_id=?',
                    (20 if combined_winner == 'local' else 10, embedded[1]['endpoint_id']))
        # This fixture configures domain policy after binding approval. Retain
        # the resulting current authority in the Connector fixture as well.
        _, current, _ = current_agent_revisions(deps.connection_factory, agent_id='subject')
        binding['configuration_revision'] = current.configuration
        binding['authorization_revision'] = current.authorization
    acknowledge_execution_binding(store, binding=R4BindingView(**binding))

    if event_recovery in ('active_disconnect', 'lease_renewal'):
        from functools import partial
        monkeypatch.setattr(executor_link, 'ExecutionLeaseService',
            partial(executor_link.ExecutionLeaseService, max_duration_ms=5000))

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
                self.stream_epoch = stream_epoch
                if one_shot:
                    from test_vertical_inventory import _Native
                    self.native = _Native()
                    assert prepared.intent.mcp_preset[0]['name'] == 'remote-preset'
                return await super().open(prepared, session_id, context, stream_epoch=stream_epoch)
        native = CountedFactory()
        native_decisions = []
        async def reply_native_approval(request, decision, response):
            native_decisions.append((request, decision, response))
        native.native.reply_native_approval = reply_native_approval
        async def environment(_):
            return {}
        async def candidates(_):
            return [candidate]
        async def launch(_):
            return R4LaunchSetup(environment)
        owner = execution = None
        completed_shutdown = None
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
            if cli_admission:
                from okto_nexus_connector.cli.main import build_parser
                from okto_nexus_connector.cli.commands.runtime import run_runtime
                from okto_nexus_connector.cli.output import Output
                action = {"runtime.start": "start", "turn.submit": "submit", "turn.steer": "steer",
                          "turn.interrupt": "interrupt", "runtime.close": "stop"}[intent]
                words = ["runtime", action]
                if intent == "runtime.start":
                    words += ["assistant", "--new-session"]
                else:
                    words += [options["session_id"]]
                    if intent in {"turn.submit", "turn.steer"}:
                        words += [options["text"]]
                    words += ["--alias", "assistant"]
                    target = options.get("target", {})
                    if target.get("kind") == "native_turn_id":
                        words += ["--expected-turn-id", target["expected_turn_id"]]
                    elif target.get("kind") == "current_run":
                        words += ["--current-run"]
                words += ["--client-intent-id", "mux-" + intent]
                args = build_parser().parse_args(words)
                admitted = await run_runtime(args, Output(json_mode=True), daemon_root)
                assert admitted["state"] == "ADMITTED", admitted
                # Repeating an acknowledged command retains the same Server
                # operation and cannot create another native effect.
                replay = await run_runtime(args, Output(json_mode=True), daemon_root)
                assert replay["operation_id"] == admitted["operation_id"]
                saved = next(r for r in daemon.store.load().runtime_intents
                             if r.client_intent_id == "mux-" + intent)
                resolution = saved.resolution
            elif domain_delivery and intent == 'turn.submit':
                from pathlib import Path
                monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
                from test_pr34_remediation import tool
                client.headers['host'] = '127.0.0.1:8000'
                created = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '),
                    'message_create', dict(workspace_id=binding['workspace_id'], from_agent_id='operator',
                        subject='Remote exclusive claim', body='Hello', target=dict(strategy='direct', agent_id='subject')))
                assert created['ok'], created
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    resolution = dict(uow.connection.execute("SELECT operation_id,intent_hash FROM execution_operations WHERE action='turn.submit'").fetchone())
                    claim = uow.connection.execute('SELECT consumer_kind,consumer_operation_id FROM message_deliveries').fetchone()
                    assert claim[0] == 'push'
                    assert uow.connection.execute('SELECT COUNT(*) FROM execution_domain_deliveries').fetchone()[0] == 1
                pulled = tool(client, headers['subject']['Authorization'].removeprefix('Bearer '),
                              'inbox_pull', dict(agent_id='subject'))
                assert pulled['ok'] and pulled['data']['messages'] == [], pulled
            else:
                actor = 'operator' if operator_containment and intent in ('turn.interrupt', 'runtime.close') else 'subject'
                resolved = (await asyncio.to_thread(client.post, '/v1/runtime/intents:resolve', headers=headers[actor], json={
                    'client_intent_id': 'mux-' + intent, 'intent': intent, 'binding_id': binding['binding_id'],
                    'workspace_binding_id': binding['workspace_binding_id'], 'agent_id': 'subject', **options}))
                assert resolved.status_code == 200, resolved.text
                resolution = resolved.json()
                assert resolution['can_submit'], resolution['blockers']
                admitted = (await asyncio.to_thread(client.post, '/v1/runtime/operations', headers=headers[actor], json={
                    k: resolution[k] for k in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')}))
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
                    observed = (await asyncio.to_thread(client.get, '/v1/runtime/operations/' + resolution['operation_id'],
                                          headers=headers['subject']))
                    assert observed.status_code == 200, observed.text
                    assert observed.json()['error'] is None, observed.json()
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
            if cli_admission:
                from okto_nexus_connector.services.binding_onboarding import BindingOnboarding
                onboarding_service = BindingOnboarding(daemon.store, daemon.vault)
                # Recover the already approved public Server proposal through
                # the same durable Connector caller used by the CLI.
                await onboarding_service.prepare(identity_alias="subject", realization_ref=binding["realization_ref"],
                    alias="assistant", client_intent_id=prepare["client_intent_id"])
                await onboarding_service.apply(identity_alias="subject", prepare_intent_id=prepare["client_intent_id"],
                    client_intent_id=apply["client_intent_id"], approved_diff_hash=apply["approved_diff_hash"],
                    operator_proof_ref=approval_id)
            from contextlib import AsyncExitStack
            async with AsyncExitStack() as stack:
                if automatic:
                    from functools import partial
                    from okto_nexus_connector.daemon import r4_control, r4_execution
                    startup_errors = []
                    original_attempt = r4_control.R4DaemonControl._attempt
                    async def diagnosed_attempt(control):
                        try:
                            return await original_attempt(control)
                        except Exception as error:
                            import traceback
                            failure = getattr(control.connection, 'failure', None)
                            startup_errors.append((type(error).__name__, getattr(error, 'code', None),
                                repr(failure), traceback.extract_tb(error.__traceback__).format()))
                            raise
                    monkeypatch.setattr(r4_control.R4DaemonControl, '_attempt', diagnosed_attempt)
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
                                raise AssertionError((control.status(), startup_errors))
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
                if one_shot:
                    from test_one_shot_remote import run_one_shot
                    await run_one_shot(deps, client, headers, binding, native, execution, monkeypatch)
                    return
                opened = await admit('runtime.start', new_session=True)
                session_id = opened['scope']['session_id']
                if combined_winner:
                    from test_combined_consumption import verify_competition
                    await verify_competition(onboarding, binding, embedded, native, execution,
                        session_id, combined_winner, monkeypatch, admit)
                    return
                if cli_admission:
                    from okto_nexus_connector.cli.main import build_parser
                    from okto_nexus_connector.cli.commands.runtime import run_runtime
                    from okto_nexus_connector.cli.output import Output
                    view = await run_runtime(build_parser().parse_args(
                        ["runtime", "inspect", session_id]), Output(json_mode=True), daemon_root)
                    assert view["scope"] == opened["scope"] and view["lifecycle_state"] == "READY"
                    assert view["process_state"] == "UNKNOWN"
                    reused = await run_runtime(build_parser().parse_args(
                        ["runtime", "start", "assistant", "--client-intent-id", "reuse-opening"] +
                        (["--text", "Initial CLI request"] if initial_prompt else [])),
                        Output(json_mode=True), daemon_root)
                    assert reused["reused"] and reused["operation_id"] == opened["operation_id"]
                    assert reused["session_id"] == session_id
                    assert reused["operation"]["client_intent_id"] == "mux-runtime.start"
                    recovered = await run_runtime(build_parser().parse_args(
                        ["runtime", "operation", "--alias", "assistant", "--client-intent-id", "reuse-opening"]),
                        Output(json_mode=True), daemon_root)
                    assert recovered == reused
                    if initial_prompt:
                        child, = reused["operation"]["follow_up_operation_ids"]
                        operations.append(child)
                        async with asyncio.timeout(8):
                            while True:
                                result = (await asyncio.to_thread(client.get, "/v1/runtime/operations/" + child, headers=headers["subject"]))
                                assert result.status_code == 200, result.text
                                if result.json()["executor_stage"] in {"SUBMITTED", "SUCCEEDED"}:
                                    break
                                assert execution.failure is None, repr(execution.failure)
                                await asyncio.sleep(.01)
                turned = await admit('turn.submit', session_id=session_id, text='Hello')
                if check_presence:
                    def presence():
                        response = client.get('/api/v1/graph', headers=headers['operator'])
                        assert response.status_code == 200, response.text
                        current = next(n['presence'] for n in response.json()['data']['nodes'] if n['agent_id'] == 'subject')
                        from test_pr34_remediation import tool
                        client.headers['host'] = '127.0.0.1:8000'
                        inspected = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '),
                                         'agent_get', {'agent_id': 'subject'})
                        assert inspected['ok'], inspected
                        assert inspected['data']['connection']['location'] == 'remote'
                        return current, inspected['data']['presence']
                    assert await asyncio.to_thread(presence) == ('present', 'present')
                    await admit('runtime.close', session_id=session_id)
                    async with asyncio.timeout(5):
                        while execution.pending_count:
                            await asyncio.sleep(.01)
                    completed_shutdown = await daemon._shutdown()
                    assert completed_shutdown == 0
                    await owner.close()
                    async with asyncio.timeout(5):
                        while await asyncio.to_thread(presence) != ('offline', 'offline'):
                            await asyncio.sleep(.05)
                    return
                if reset_active:
                    response = await asyncio.to_thread(client.post, '/api/v1/admin/reset', headers=headers['operator'])
                    assert response.status_code in (200, 202), response.text
                    async with asyncio.timeout(35):
                        while response.json()['data'].get('pending'):
                            await asyncio.sleep(.05)
                            response = await asyncio.to_thread(client.get, '/api/v1/admin/reset', headers=headers['operator'])
                            assert response.status_code == 200, response.text
                    assert native.native.stopped
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 0
                        assert uow.connection.execute('SELECT COUNT(*) FROM execution_bindings').fetchone()[0] == 1
                    from test_vertical_inventory import _Native
                    native.native = _Native()
                    restarted = await admit('runtime.start', new_session=True)
                    await admit('turn.submit', session_id=restarted['scope']['session_id'], text='After reset')
                    assert len(native.native.sent) == 1
                    await admit('runtime.close', session_id=restarted['scope']['session_id'])
                    return
                if native_decision is not None:
                    from nexus_connector_core import RuntimeEvent
                    kind, choice = native_decision
                    request = dict(schema_version=1, request_id=7, request_hash='a'*64,
                        method='item/tool/requestUserInput' if kind == 'input' else 'item/commandExecution/requestApproval',
                        params={'threadId':'native-thread','turnId':'turn-from-native','itemId':'item'})
                    if kind == 'input':
                        request['params'].update(isBlocking=True,questions=[
                            {'id':'question','header':'Response','question':'Provide input.','isOther':True}])
                    await native.native.queue.put(RuntimeEvent(server_id, executor_id, session_id,
                        native.stream_epoch, 0, 'input_request' if kind == 'input' else 'approval_request',
                        request['method'], {'native_approval':request, 'native_approval_display':dict(request)},
                        turned['operation_id']))
                    async with asyncio.timeout(8):
                        while True:
                            queued = (await asyncio.to_thread(client.get, '/api/v1/approvals', headers=headers['operator'],
                                params={'workspace':binding['workspace_id'],'status':'pending'}))
                            assert queued.status_code == 200, queued.text
                            rows = [row for row in queued.json()['data']['items'] if row['action']=='execution.native.respond']
                            if rows: break
                            assert execution.failure is None, repr(execution.failure)
                            await asyncio.sleep(.01)
                    assert len(rows) == 1
                    detail = (await asyncio.to_thread(client.get, '/api/v1/approvals/'+rows[0]['approval_id'],headers=headers['operator']))
                    proposal = detail.json()['data']['request_payload']['kwargs']
                    body = {k:proposal[k] for k in ('approval_key','expected_revision','request_hash','cas_token')}
                    body.update(client_intent_id='remote-native-decision',decision=choice)
                    response = {'answers':{'question':{'answers':['remote-private-input-marker']}}} if kind=='input' and choice=='approve' else None
                    if response is not None: body['response']=response
                    # Native input belongs to its recipient; execution
                    # permission decisions belong to the operator.
                    responder = headers['subject' if kind == 'input' else 'operator']
                    forbidden = headers['operator' if kind == 'input' else 'subject']
                    assert (await asyncio.to_thread(client.post, '/v1/runtime/approval-decisions',headers=forbidden,json=body)).status_code == 403
                    confirmed = (await asyncio.to_thread(client.post, '/v1/runtime/approval-decisions',headers=responder,json=body))
                    assert confirmed.status_code == 202, confirmed.text
                    decision = confirmed.json()
                    repeated = (await asyncio.to_thread(client.post, '/v1/runtime/approval-decisions',headers=responder,json=body))
                    assert repeated.status_code == 200, repeated.text
                    assert repeated.json()['native_operation_id'] == decision['native_operation_id']
                    operations.append(decision['native_operation_id'])
                    async with asyncio.timeout(8):
                        while True:
                            result = (await asyncio.to_thread(client.get, '/v1/runtime/approval-decisions/'+decision['decision_id'],headers=headers['operator']))
                            assert result.status_code == 200, result.text
                            view = result.json()
                            if view['native_stage']=='SUBMITTED': break
                            assert view['native_stage']=='DISPATCH_PENDING', view
                            assert execution.failure is None, repr(execution.failure)
                            await asyncio.sleep(.01)
                    assert view['canonical_state'] == ('CONFIRMED' if choice=='approve' else 'DENIED')
                    assert len(native_decisions) == 1
                    frozen_request = {key: request[key] for key in ('request_id','request_hash','method','params')}
                    expected_decision = 'accept' if choice=='approve' else 'cancel' if kind=='input' else 'decline'
                    assert native_decisions[0] == (frozen_request,expected_decision,response)
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        assert 'remote-private-input-marker' not in '\n'.join(uow.connection.iterdump())
                if event_recovery == 'active_disconnect':
                    import time
                    await owner.close()
                    runtime = next(iter(execution._sessions.values())).runtime
                    installed_deadline = runtime.r4_operation_context(dispatched['turn.submit'],
                        connection_id=owner.state.connection_id,
                        connection_generation=owner.state.connection_generation).lease_deadline_monotonic
                    async with asyncio.timeout(3):
                        while not control.cleanup_pending:
                            await asyncio.sleep(.01)
                    assert time.monotonic() < installed_deadline
                    assert not native.native.stopped and daemon.host._journal is not None
                    assert not control.status()['execution_ready']
                    async with asyncio.timeout(8):
                        while not native.native.stopped:
                            await asyncio.sleep(.01)
                    assert time.monotonic() >= installed_deadline
                    generation = owner.state.connection_generation
                    async with asyncio.timeout(15):
                        while not (control.status()['execution_ready'] and control.connection.state.connection_generation > generation):
                            await asyncio.sleep(.01)
                    assert native.opens == 1
                    assert [kind for kind, _ in native.native.sent] == ['send_turn']
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 2
                        assert uow.connection.execute('SELECT COUNT(*) FROM execution_dispatch_outbox WHERE attempt_no<>1').fetchone()[0] == 0
                        assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()) == ('CLOSED','CLOSED')
                        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='runtime.close'").fetchone()[0] == 0
                        assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts').fetchone()[0] == 2
                    return
                if event_recovery == 'lease_renewal':
                    import time
                    initial_deadline = native.context.lease_deadline_monotonic
                    async with asyncio.timeout(10):
                        while time.monotonic() <= initial_deadline + .05:
                            assert not native.native.stopped and control.status()['execution_ready']
                            await asyncio.sleep(.02)
                    runtime = next(iter(execution._sessions.values())).runtime
                    current = runtime.r4_operation_context(dispatched['turn.submit'],
                        connection_id=owner.state.connection_id,
                        connection_generation=owner.state.connection_generation)
                    assert current.r4_authority.lease_serial >= 2
                    assert current.lease_deadline_monotonic > initial_deadline
                    assert native.opens == 1 and not native.native.stopped
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        row = uow.connection.execute(
                            'SELECT lease_serial,status FROM execution_leases ORDER BY lease_serial DESC LIMIT 1').fetchone()
                        assert row['lease_serial'] >= 2 and row['status'] == 'ACTIVE'
                if native_decision is None and ((automatic and event_recovery != 'lease_renewal') or (reconcile_closed and not publication_failure and not history_count)):
                    from nexus_connector_core import RuntimeEvent
                    journal = await daemon.host.ensure_history_journal()
                    original_ack = journal.acknowledge_events
                    ack_attempts = []
                    async def interrupted_ack(cursor, through):
                        ack_attempts.append(through)
                        if len(ack_attempts) == 1:
                            raise OSError('Injected Core ACK write failure after Server commit.')
                        return await original_ack(cursor, through)
                    if event_recovery:
                        publish_events = owner.publish_events
                        async def interrupted_events(**values):
                            if event_recovery.endswith('ack_lost'):
                                await publish_events(**values)
                            raise OSError('Injected event delivery interruption.')
                        monkeypatch.setattr(owner,'publish_events',interrupted_events)
                    else:
                        monkeypatch.setattr(journal, 'acknowledge_events', interrupted_ack)
                    await native.native.queue.put(RuntimeEvent(server_id,executor_id,session_id,native.stream_epoch,
                        0,'text_delta','synthetic.delta',{'text':'Automatic event publication.'},turned['operation_id']))
                    stream = dict(server_id=server_id,executor_id=executor_id,binding_id=binding['binding_id'],
                                  agent_id='subject',session_id=session_id,stream_epoch=native.stream_epoch)
                    if event_recovery:
                        from nexus_connector_core import EventCursor
                        async with asyncio.timeout(5):
                            while await journal.contiguous_watermark(EventCursor(server_id,executor_id,session_id,native.stream_epoch)) < 1:
                                await asyncio.sleep(.01)
                            while not execution.events.errors:
                                await asyncio.sleep(.01)
                        progress = await asyncio.to_thread(execution.events.store.read,stream)
                        assert progress['remote_acked'] == progress['core_applied'] == 0
                    else:
                        async with asyncio.timeout(5):
                            while True:
                                try:
                                    progress = await asyncio.to_thread(execution.events.store.read,stream)
                                except ConnectorError:
                                    progress = {'core_applied':0}
                                if progress['core_applied'] == 1:
                                    break
                                await asyncio.sleep(.01)
                        assert progress['remote_acked'] == 1 and ack_attempts == [1,1]
                        assert not execution.events.errors
                        with deps.connection_factory.unit_of_work(write=False) as uow:
                            assert uow.connection.execute('SELECT COUNT(*) FROM execution_event_ingress').fetchone()[0] == 1
                            assert tuple(uow.connection.execute('SELECT committed_contiguous,projected_through FROM execution_event_watermarks').fetchone()) == (1,0)
                await admit('turn.steer', session_id=session_id, text='Continue carefully.',
                    target={'kind': 'native_turn_id', 'expected_turn_id': 'turn-from-native'})
                if operator_containment:
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        profile = dict(uow.connection.execute('SELECT p.* FROM runtime_profiles p JOIN agent_endpoints e '
                            'ON e.profile_id=p.profile_id WHERE e.endpoint_id=?', (binding['endpoint_id'],)).fetchone())
                    disabled = await asyncio.to_thread(client.patch, '/api/v1/harness/profiles/' + profile['profile_id'],
                        headers=headers['operator'], json=dict(expected_revision=profile['revision'], enabled=False))
                    assert disabled.status_code == 200, disabled.text
                await admit('turn.interrupt', session_id=session_id,
                    target={'kind': 'current_run', 'expected_turn_id': None})
                await admit('runtime.close', session_id=session_id)
                async with asyncio.timeout(5):
                    while execution.pending_count:
                        await asyncio.sleep(0)
                if event_recovery and event_recovery != 'lease_renewal':
                    generation = owner.state.connection_generation
                    old_ticket = control.execution.lanes[binding['binding_id']].ticket.ticket_id
                    if event_recovery.startswith('cold_'):
                        assert await daemon._shutdown() == 0
                        daemon = DaemonApp(daemon_root)
                        daemon._start_transports()
                        control = daemon.r4_controls[server_id]
                        assert not control._retained_lanes
                    else:
                        await owner.close()
                    async with asyncio.timeout(15):
                        while not (control.status()['execution_ready'] and control.connection.state.connection_generation > generation):
                            await asyncio.sleep(.01)
                    owner = control.connection
                    execution = control.execution.owner
                    progress = await asyncio.to_thread(execution.events.store.read,stream)
                    assert progress['remote_acked'] == progress['core_applied'] == 1
                    assert control._retained_lanes and owner.is_attached(binding_id=binding['binding_id'],agent_id='subject',
                        credential_epoch=revisions.credential_epoch,authorization_revision=binding['authorization_revision'],
                        configuration_revision=binding['configuration_revision'])
                    with deps.connection_factory.unit_of_work(write=False) as uow:
                        assert uow.connection.execute('SELECT COUNT(*) FROM execution_event_ingress').fetchone()[0] == 1
                        assert uow.connection.execute('SELECT committed_contiguous FROM execution_event_watermarks').fetchone()[0] == 1
                        if event_recovery.startswith('cold_'):
                            rows = uow.connection.execute(
                                'SELECT ticket_id,client_intent_id,replaces_ticket_id,revoked_at FROM execution_link_tickets WHERE binding_id=?',
                                (binding['binding_id'],)).fetchall()
                            assert len(rows) == 2
                            old = next(row for row in rows if row['ticket_id'] == old_ticket)
                            new = next(row for row in rows if row['ticket_id'] != old_ticket)
                            assert old['revoked_at'] is not None and new['revoked_at'] is None
                            assert new['replaces_ticket_id'] == old_ticket
                            assert new['client_intent_id'] == old['client_intent_id']
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
                    final = (await asyncio.to_thread(client.get, '/v1/runtime/operations/' + operations[-1], headers=headers['subject'])).json()
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
            if cli_admission:
                from okto_nexus_connector.cli.main import build_parser
                from okto_nexus_connector.cli.commands.runtime import run_runtime
                from okto_nexus_connector.cli.output import Output
                retained = daemon.store.load().runtime_intents
                assert len(retained) == 6
                daemon.store.update(lambda state: state.binding_intents.clear())
                inspected = await run_runtime(build_parser().parse_args(
                    ["runtime", "inspect", session_id]), Output(json_mode=True), daemon_root)
                assert inspected["lifecycle_state"] == "CLOSED"
                assert not inspected["control_available"] and inspected["process_state"] == "UNKNOWN"
                status = await run_runtime(build_parser().parse_args(
                    ["runtime", "status", "--alias", "assistant"]), Output(json_mode=True), daemon_root)
                assert status == {"sessions": [inspected]}
                for record in retained:
                    args = build_parser().parse_args(["runtime", "operation", "--alias", "assistant",
                                                      "--client-intent-id", record.client_intent_id])
                    view = await run_runtime(args, Output(json_mode=True), daemon_root)
                    assert view["operation"]["receipt_revision"] == 1
                    assert view["operation"]["error"] is None
            assert [kind for kind, _ in native.native.sent] == (['send_turn'] if initial_prompt else []) + ['send_turn', 'steer', 'interrupt']
            with deps.connection_factory.unit_of_work(write=False) as uow:
                if initial_prompt:
                    assert uow.connection.execute("SELECT SUM(used_executions) FROM runtime_execution_grants").fetchone()[0] == 3
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 5 + history_count + bool(native_decision) + bool(initial_prompt)
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_receipts').fetchone()[0] == 5 + history_count + bool(native_decision) + bool(initial_prompt)
                assert uow.connection.execute('SELECT COUNT(*) FROM execution_dispatch_outbox WHERE attempt_no<>1').fetchone()[0] == 0
                expected_session = ('READY', 'SUPERSEDED') if publication_failure in ('before_commit', 'core_commit') and not reconcile_closed else ('CLOSED', 'CLOSED')
                # Receipt ingress preserves history after disconnect. Adoption
                # of that fact into session readiness remains reconciliation.
                assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()) == expected_session
                if operator_containment:
                    assert not uow.connection.execute('SELECT 1 FROM runtime_execution_grants WHERE revoked_at IS NULL').fetchone()
                    controls = uow.connection.execute("SELECT actor_agent_id,subject_agent_id FROM execution_operations "
                        "WHERE action IN ('turn.interrupt','runtime.close')").fetchall()
                    assert [tuple(r) for r in controls] == [('operator','subject'),('operator','subject')]
        finally:
            try:
                if recovery_host is not None:
                    await recovery_host.shutdown_all()
                result = await daemon._shutdown() if completed_shutdown is None else completed_shutdown
                if owner is not None:
                    await owner.close()
                assert result == (1 if publication_failure else 0)
            finally:
                server.should_exit = True
                await asyncio.wait_for(serving, 5)
                sock.close()
    asyncio.run(run())


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
def test_reset_stops_remote_execution_and_reuses_connection(onboarding, tmp_path, monkeypatch):
    test_owned_connector_reader_dispatches_five_actions_over_real_websocket(
        onboarding, tmp_path, monkeypatch, True, None, False, 0, None, reset_active=True)


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
def test_remote_operator_contains_session_after_profile_revocation(onboarding, tmp_path, monkeypatch):
    test_owned_connector_reader_dispatches_five_actions_over_real_websocket(
        onboarding, tmp_path, monkeypatch, True, None, False, 0, None, operator_containment=True)


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
def test_graph_presence_tracks_remote_connector_disconnect(onboarding, tmp_path, monkeypatch):
    test_owned_connector_reader_dispatches_five_actions_over_real_websocket(
        onboarding, tmp_path, monkeypatch, False, None, False, 0, None, check_presence=True)


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
def test_remote_domain_delivery_keeps_exclusive_claim_from_mcp(onboarding, tmp_path, monkeypatch):
    test_owned_connector_reader_dispatches_five_actions_over_real_websocket(
        onboarding, tmp_path, monkeypatch, True, None, False, 0, None, domain_delivery=True)


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
@pytest.mark.parametrize('kind,choice', [('approval','approve'),('approval','deny'),('input','approve'),('input','deny')])
def test_canonical_native_decision_roundtrip_through_automatic_connector(onboarding, tmp_path, monkeypatch, kind, choice):
    test_owned_connector_reader_dispatches_five_actions_over_real_websocket(
        onboarding,tmp_path,monkeypatch,True,None,False,0,None,native_decision=(kind,choice))


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
def test_public_runtime_cli_dispatches_five_actions_through_automatic_daemon(onboarding, tmp_path, monkeypatch):
    test_owned_connector_reader_dispatches_five_actions_over_real_websocket(
        onboarding, tmp_path, monkeypatch, True, None, False, 0, None, cli_admission=True)


@pytest.mark.parametrize('onboarding', ['connector-configured'], indirect=True)
def test_public_runtime_cli_start_prompt_runs_as_child(onboarding, tmp_path, monkeypatch):
    test_owned_connector_reader_dispatches_five_actions_over_real_websocket(
        onboarding, tmp_path, monkeypatch, True, None, False, 0, None,
        cli_admission=True, initial_prompt=True)
