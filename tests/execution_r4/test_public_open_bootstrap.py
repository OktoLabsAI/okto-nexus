"""Public onboarding/admission through Core open with a synthetic native peer.

Only identities are seeded. The WSS owner dispatches the admitted outbox.
The qualification gate/native peer are synthetic: no daemon or provider claim.
"""

import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest
from nexus_connector_core import (
    CoreError, ControlOperation, InstallationCandidate, LaunchIntent, OpenOperation,
    R4_PREVIEW_REVISION, ShutdownPolicy, TurnOperation, create_runtime,
    decode_r4_frame, encode_r4_frame, r4_close_operation,
)
from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.journal import open_journal

from okto_nexus.adapters.inbound.http import executor_link, runtime_v1
from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from okto_nexus.domain.base import iso_plus

from test_binding_operator import onboarding, prepare_delegated, decide_binding
from test_ns09 import negotiate
from test_vertical_inventory import _NativeFactory


@pytest.mark.parametrize('disconnect_after_bootstrap', [False, True])
def test_public_binding_grant_admission_bootstrap_core_and_receipts(onboarding, tmp_path, monkeypatch, disconnect_after_bootstrap):
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
        'actions': ['open', 'send', 'steer', 'interrupt', 'close'], 'max_executions': 2,
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
        assert replay.status_code == 200
        assert replay.json()['operation_id'] == submitted.json()['operation_id'] == resolution['operation_id']
        # Delivery comes from the Server's owned loop, without a test call to
        # reserve/begin or a manually constructed operation frame.
        frame = ws.receive_json()
        assert frame['type'] == 'operation.submit'
        assert frame['operation_id'] == resolution['operation_id']
        assert frame['intent_hash'] == resolution['intent_hash']
        assert frame['connection_id'] == channel.connection_id
        return resolution, SimpleNamespace(frame=frame, scope=resolution['scope'], grant_id=frame['grant_id'])

    with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
            headers={'Authorization': f'Bearer {link}'}, subprotocols=['nxl.v1']) as ws:
        channel = negotiate(ws, info, revisions, lane, server, executor, binding_id=binding['binding_id'])
        resolution, sent = admit_public('open-public', 'runtime.start', new_session=True)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            dispatched = uow.connection.execute(
                'SELECT dispatch_phase,reservation_owner,reservation_generation FROM execution_dispatch_outbox').fetchone()
            assert tuple(dispatched) == ('OPEN_AUTHORIZED_PENDING_LEASE', channel.connection_id, channel.connection_generation)
        assert sent.grant_id == canonical['grant_id']
        if disconnect_after_bootstrap:
            ws.close()
            deadline = time.monotonic() + 3
            while True:
                observed = client.get(f"/v1/runtime/operations/{resolution['operation_id']}", headers=headers['subject']).json()
                if observed['admission_state'] == 'RECONCILING':
                    break
                assert time.monotonic() < deadline
                time.sleep(0.01)
            assert observed['possible_effect'] and not observed['retry_safe']
            assert observed['executor_stage'] is None and observed['receipt_revision'] == 0
            assert observed['error']['code'] == 'DISPATCH_CONNECTION_LOST'
            repeated = client.post('/v1/runtime/operations', headers=headers['subject'], json={
                k: resolution[k] for k in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')})
            assert repeated.status_code == 200 and repeated.json()['operation_id'] == resolution['operation_id']
            with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
                    headers={'Authorization': f'Bearer {link}'}, subprotocols=['nxl.v1']) as reconnect:
                base = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, server_id=server, executor_id=executor)
                reconnect.send_text(encode_r4_frame(dict(**base, type='hello', link_attempt_id='reconnect',
                    core_version=info['core_version'], management_revision=info['management_revision'],
                    supported_nxl=[R4_PREVIEW_REVISION], snapshot_formats=[info['executor_snapshot_format']],
                    control_capabilities=[])).decode())
                welcome = reconnect.receive_json()
                pending = reconnect.receive_json()
                assert pending['operation_ids'] == [resolution['operation_id']]
                assert pending['session_ids'] == [sent.scope['session_id']]
                reconnect.send_text(encode_r4_frame(dict(**base, type='reconcile.report',
                    connection_id=welcome['connection_id'], connection_generation=welcome['connection_generation'],
                    reconcile_id=pending['reconcile_id'], cursor=None, next_cursor=None, complete=True,
                    receipts=[], claims=[], stream_watermarks=[], ownership_facts=[])).decode())
                assert reconnect.receive_json()['recovery_remaining'] is True
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 1
                    assert uow.connection.execute('SELECT COUNT(*) FROM execution_leases').fetchone()[0] == 0
                    assert tuple(uow.connection.execute('SELECT dispatch_state,attempt_no FROM execution_dispatch_outbox').fetchone()) == ('RECONCILING', 1)
            return

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
                        # A gap is stored without a false ACK; filling it commits
                        # the contiguous prefix before the WSS response is visible.
                        event_base = dict(server_id=server,executor_id=executor,
                            session_id=sent.scope["session_id"],stream_epoch="public-epoch",
                            category="text_delta",payload={"text":"Hello"},operation_id=opened.operation_id)
                        batch = dict(protocol_major=1,contract_revision=R4_PREVIEW_REVISION,type="event.batch",
                            server_id=server,executor_id=executor,binding_id=binding["binding_id"],agent_id="subject",
                            session_id=sent.scope["session_id"],stream_epoch="public-epoch",
                            connection_id=channel.connection_id,connection_generation=channel.connection_generation)
                        await peer.send(encode_r4_frame({**batch,"events":[{**event_base,"sequence":2}]}).decode())
                        await peer.send(encode_r4_frame({**batch,"events":[{**event_base,"sequence":1}]}).decode())
                        ack = decode_r4_frame((await peer.recv()).encode())
                        assert ack["type"] == "event.ack" and ack["sequence"] == 2
                        with deps.connection_factory.unit_of_work(write=False) as uow:
                            assert uow.connection.execute("SELECT COUNT(*) FROM execution_event_ingress").fetchone()[0] == 2
                            assert tuple(uow.connection.execute("SELECT committed_contiguous,projected_through,gap_state "
                                "FROM execution_event_watermarks").fetchone()) == (2,0,"none")
                        await peer.send(encode_r4_frame({**batch,"events":[{**event_base,"sequence":1}]}).decode())
                        assert decode_r4_frame((await peer.recv()).encode())["sequence"] == 2
                        turn, dispatched = admit_public('turn-public', 'turn.submit', session_id=sent.scope['session_id'], text='Hello')
                        turn_context = runtime.r4_operation_context(dispatched.frame, connection_id=channel.connection_id,
                                                                   connection_generation=channel.connection_generation)
                        receipt = await runtime.submit(TurnOperation(turn['operation_id'], sent.scope['session_id'], 'Hello'), turn_context)
                        await http.publish_core_turn_receipt(lane, submit_frame=dispatched.frame,
                            core_receipt=receipt, context=turn_context, receipt_revision=1)
                        native_target = {'kind': 'native_turn_id', 'expected_turn_id': 'turn-from-native'}
                        steer, steered = admit_public('steer-public', 'turn.steer', session_id=sent.scope['session_id'],
                                                      text='Continue carefully.', target=native_target)
                        steer_context = runtime.r4_operation_context(steered.frame, connection_id=channel.connection_id,
                                                                    connection_generation=channel.connection_generation)
                        steering = ControlOperation(steer['operation_id'], sent.scope['session_id'], 'steer',
                            text=steered.frame['payload']['text'], expected_turn_id=steered.frame['expected_turn_id'])
                        steering_receipt = await runtime.control(steering, steer_context)
                        await http.publish_core_steer_receipt(lane, submit_frame=steered.frame,
                            core_receipt=steering_receipt, context=steer_context, receipt_revision=1)
                        interrupt, interrupted = admit_public('interrupt-public', 'turn.interrupt',
                            session_id=sent.scope['session_id'], target={'kind': 'current_run', 'expected_turn_id': None})
                        interrupt_context = runtime.r4_operation_context(interrupted.frame, connection_id=channel.connection_id,
                                                                        connection_generation=channel.connection_generation)
                        interruption = ControlOperation(interrupt['operation_id'], sent.scope['session_id'], 'interrupt',
                                                         reason=interrupted.frame['payload']['reason'])
                        interruption_receipt = await runtime.control(interruption, interrupt_context)
                        await http.publish_core_interrupt_receipt(lane, submit_frame=interrupted.frame,
                            core_receipt=interruption_receipt, context=interrupt_context, receipt_revision=1)
                        close, closed = admit_public('close-public', 'runtime.close', session_id=sent.scope['session_id'])
                        close_context = runtime.r4_operation_context(closed.frame, connection_id=channel.connection_id,
                                                                    connection_generation=channel.connection_generation)
                        close_receipt = await runtime.close(r4_close_operation(closed.frame), close_context)
                        await http.publish_core_close_receipt(lane, submit_frame=closed.frame,
                            core_receipt=close_receipt, context=close_context, receipt_revision=1)
                assert native.native.sent == [('send_turn', turn['operation_id']), ('steer', steer['operation_id']),
                                              ('interrupt', interrupt['operation_id'])]
                assert native.native.stopped
                observed = client.get(f"/v1/runtime/operations/{turn['operation_id']}", headers=headers['subject'])
                assert observed.status_code == 200 and observed.json()['executor_stage'] == receipt.stage
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    conn = uow.connection
                    assert conn.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 5
                    assert conn.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0] == 1
                    assert conn.execute('SELECT used_executions FROM runtime_execution_grants').fetchone()[0] == 2
                    assert tuple(conn.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()) == ('CLOSED', 'CLOSED')
                    assert conn.execute("SELECT COUNT(*) FROM execution_dispatch_outbox WHERE dispatch_state='PENDING'").fetchone()[0] == 0
                    assert conn.execute("SELECT COUNT(*) FROM execution_dispatch_outbox WHERE attempt_no<>1").fetchone()[0] == 0
            finally:
                await runtime.shutdown(ShutdownPolicy(0, 0))
                await journal.aclose()
        asyncio.run(run())
