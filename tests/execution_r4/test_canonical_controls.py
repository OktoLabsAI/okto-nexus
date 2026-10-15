"""Public HTTP controls with installed Core and a strict native test peer.

Approved selection and qualification are fixtures. Resolution, admission,
policy, leases, dispatch, effects and receipt ingress use their real services.
This campaign does not qualify providers, the daemon or separate hosts.
"""

import asyncio
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from nexus_connector_core import (
    ControlOperation, CoreError, LaunchIntent, OpenOperation, OperationKey, ShutdownPolicy,
    create_runtime, r4_close_operation, r4_lease_renew_frame, r4_submit_intent_hash,
)
from nexus_connector_core.journal import open_journal

from okto_nexus.adapters.inbound.http import runtime_v1
from okto_nexus.adapters.outbound.sqlite.execution_tickets import issue_execution_ticket
from okto_nexus.application.execution_dispatch import (
    begin_execution_send, release_unsent_dispatch, reserve_execution_dispatch,
)
from okto_nexus.application.execution_leases import ExecutionLeaseService
from okto_nexus.application.execution_semantics import (
    execution_intent_hash, execution_wire_intent, validate_execution_target,
)
from okto_nexus.errors import OktoNexusError
from test_ns09 import negotiate, setup_authority
from test_vertical_inventory import _NativeFactory


@pytest.mark.parametrize('adapter,action,kind,turn,valid', [
    ('codex_app_server', 'turn.steer', 'native_turn_id', 't', True),
    ('codex_app_server', 'turn.steer', 'current_run', None, False),
    ('codex_app_server', 'turn.interrupt', 'current_run', None, True),
    ('codex_app_server', 'turn.interrupt', 'none', None, False),
    ('pi_rpc', 'turn.steer', 'current_run', None, True),
    ('pi_rpc', 'turn.interrupt', 'native_turn_id', 't', False),
    ('claude_stream', 'turn.steer', 'current_run', None, True),
    ('claude_stream', 'turn.interrupt', 'current_run', None, True),
    ('claude_attach', 'turn.interrupt', 'current_run', None, False),
    ('codex_app_server', 'turn.submit', 'current_run', None, False),
])
def test_targeting_uses_core_contract(adapter, action, kind, turn, valid):
    target = dict(kind=kind, expected_turn_id=turn)
    if valid:
        validate_execution_target(adapter, action, target)
    else:
        with pytest.raises(OktoNexusError):
            validate_execution_target(adapter, action, target)


def test_native_target_is_bound_to_the_wire_hash():
    semantic = dict(server_id='s', executor_id='e', binding_id='b', agent_id='a',
        workspace_id='w', workspace_binding_id='wb', session_id='ss',
        configuration_revision=1, action='turn.steer', payload={'text':'Continue'},
        target={'kind':'native_turn_id', 'expected_turn_id':'turn-a'})
    first = execution_intent_hash(semantic)
    assert first == r4_submit_intent_hash(execution_wire_intent(semantic))
    assert 'target' not in execution_wire_intent(semantic)
    assert first != execution_intent_hash({**semantic,
        'target':{'kind':'native_turn_id', 'expected_turn_id':'turn-b'}})


@pytest.mark.parametrize('finish', ['revoke', 'close'])
def test_public_controls_preserve_ids_authority_and_expired_containment(tmp_path, monkeypatch, finish):
    pytest.importorskip('okto_nexus_connector')
    from okto_nexus_connector.transport.https_client import NexusHTTPClient
    values = setup_authority(tmp_path, monkeypatch,
        actions=['open','send','steer','interrupt','close'], max_executions=3)
    deps, app, access, operator, canonical, candidate, info, revisions, link, lane, server, executor = values
    # The product qualification flag stays false outside this contract test.
    monkeypatch.setattr(runtime_v1, 'protocol_info', lambda: {**info, 'remote_execution_ready':True})
    factory = deps.connection_factory
    fresh = app.state.inventory_fresh_publications
    key = app.state.test_agent_keys['subject']
    def reserve():
        return reserve_execution_dispatch(factory, server_id=server, executor_id=executor,
                                          remote_ready=True, regular_items=1)
    def dispatch(reservation):
        return begin_execution_send(factory, reservation=reservation, remote_ready=True,
                                    fresh_publications=fresh, access=access)
    class Clock:
        now = 100.0
        def monotonic(self): return self.now
        def wall_time(self): return self.now
    clock = Clock()
    original_clock = access.clock
    class ServerClock:
        offset = 0
        def now_iso(self):
            return (datetime.fromisoformat(original_clock.now_iso().replace('Z','+00:00'))
                    + timedelta(seconds=self.offset)).isoformat()
    server_clock = ServerClock()
    monkeypatch.setattr(access, 'clock', server_clock)
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(f'wss://127.0.0.1:8202/v1/runtime/executors/{executor}/link',
                headers={'Authorization':f'Bearer {link}'}, subprotocols=['nxl.v1']) as ws:
            channel = negotiate(ws, info, revisions, lane, server, executor)
            async def run():
                journal = await open_journal(tmp_path / 'controls.db')
                native = _NativeFactory()
                original_send = native.native.send
                async def checked_send(verb, payload, operation_id, *, expected_turn_id=None):
                    if expected_turn_id is not None and expected_turn_id != native.native.active_turn_id:
                        raise CoreError('STALE_GENERATION', 'native_target', retry_safe=True)
                    await original_send(verb, payload, operation_id, expected_turn_id=expected_turn_id)
                native.native.send = checked_send
                async def environment(_): return {}
                runtime = create_runtime(journal=journal, environment=environment, clock=clock,
                    lease_poll_seconds=3600, candidates={candidate.adapter_id:candidate},
                    workspace_roots={'ws':str(tmp_path)}, native_factory=native)
                try:
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False)) as raw:
                        async with NexusHTTPClient('https://127.0.0.1:8202', client=raw) as http:
                            opening = await http.resolve_r4_intent(key, client_intent_id='open',
                                intent='runtime.start', binding_id='binding', workspace_binding_id='wxb', new_session=True)
                            assert opening.can_submit, opening.blockers
                            await http.submit_r4_operation(key, opening)
                            scope = opening.scope
                            lease_service = ExecutionLeaseService(factory=factory, access=access,
                                fresh_publications=fresh, max_duration_ms=10000)
                            attempt = await runtime.begin_r4_lease_request(scope=scope,
                                grant_id=canonical['grant_id'], connection_id=channel.connection_id,
                                connection_generation=channel.connection_generation, purpose='initial')
                            granted = lease_service.issue(r4_lease_renew_frame(attempt), channel=channel)
                            installed = await runtime.install_r4_lease(attempt, granted)
                            lease_service.applied(installed.acknowledgement, channel=channel)
                            sent = dispatch(reserve())
                            prepared = await runtime.prepare(LaunchIntent('subject','ws',candidate.adapter_id), installed.context)
                            opened = await runtime.open(OpenOperation(opening.operation_id, scope['session_id'], 'epoch', prepared), installed.context)
                            ticket = issue_execution_ticket(factory, server_id=server, executor_id=executor,
                                binding_id='binding', agent_id='subject', scopes=frozenset({'receipt:publish'})).ticket
                            await http.publish_core_open_receipt(ticket, submit_frame=sent.frame,
                                core_receipt=opened, context=installed.context, prepared=prepared,
                                stream_epoch='epoch', receipt_revision=1)

                            async def resolve(intent, name, *, target=None, text=None):
                                return await http.resolve_r4_intent(key, client_intent_id=name,
                                    intent=intent, binding_id='binding', workspace_binding_id='wxb',
                                    session_id=scope['session_id'], text=text, target=target)
                            native_target = {'kind':'native_turn_id', 'expected_turn_id':'turn-from-native'}
                            current_run = {'kind':'current_run', 'expected_turn_id':None}
                            # Invalid shapes fail before any operation or outbox is created.
                            for target in ({}, {'kind':'none','expected_turn_id':None},
                                           {'kind':'current_run','expected_turn_id':None},
                                           {'kind':[], 'expected_turn_id':None}):
                                response = await raw.post('https://127.0.0.1:8202/v1/runtime/intents:resolve',
                                    headers={'Authorization':f'Bearer {key}'}, json=dict(
                                    client_intent_id='invalid', intent='turn.steer', binding_id='binding',
                                    workspace_binding_id='wxb', session_id=scope['session_id'], text='Continue', target=target))
                                assert response.status_code == 422, response.text

                            queued = await resolve('turn.submit', 'queued', text='Queued work')
                            await http.submit_r4_operation(key, queued)
                            held = reserve()  # Fill the regular lane; control still progresses.
                            steer_text = 'Continue carefully. ' * 1000
                            steer = await resolve('turn.steer', 'steer', text=steer_text, target=native_target)
                            assert steer.can_submit
                            await http.submit_r4_operation(key, steer)
                            assert (await http.submit_r4_operation(key, steer))['operation_id'] == steer.operation_id
                            control = reserve()
                            assert control.reservation_class == 'control'
                            assert 16 * 1024 < control.reserved_bytes <= 128 * 1024
                            authorized = dispatch(control)
                            assert authorized.frame['intent_hash'] == steer.intent_hash
                            assert authorized.frame['expected_turn_id'] == 'turn-from-native'
                            with pytest.raises(OktoNexusError, match='reservation changed'):
                                dispatch(control)
                            context = runtime.r4_operation_context(authorized.frame, connection_id=channel.connection_id,
                                connection_generation=channel.connection_generation)
                            operation = ControlOperation(steer.operation_id, scope['session_id'], 'steer',
                                text=steer_text, expected_turn_id='turn-from-native')
                            receipt = await runtime.control(operation, context)
                            assert await runtime.control(operation, context) == receipt
                            await http.publish_core_steer_receipt(ticket, submit_frame=authorized.frame,
                                core_receipt=receipt, context=context, receipt_revision=1)
                            assert native.native.sent == [('steer', steer.operation_id)]

                            # Wrong actual target is refused by the strict native peer.
                            wrong = await resolve('turn.steer', 'wrong-target', text='Continue',
                                target={'kind':'native_turn_id','expected_turn_id':'old-turn'})
                            await http.submit_r4_operation(key, wrong)
                            wrong_dispatch = dispatch(reserve())
                            with pytest.raises(CoreError, match='STALE_GENERATION'):
                                await runtime.control(ControlOperation(wrong.operation_id,
                                    scope['session_id'], 'steer', text='Continue', expected_turn_id='old-turn'), context)
                            wrong_receipt = await journal.get_receipt(OperationKey(server, executor, wrong.operation_id))
                            assert wrong_receipt.stage == 'FAILED'
                            await http.publish_core_steer_receipt(ticket, submit_frame=wrong_dispatch.frame,
                                core_receipt=wrong_receipt, context=context, receipt_revision=1)
                            assert len(native.native.sent) == 1

                            # Productive lease expiry is independent of the still-valid
                            # canonical grant and lane. Advance both injected clocks,
                            # without changing persisted grants or authority.
                            clock.now = installed.context.lease_deadline_monotonic + 0.01
                            server_clock.offset = 11
                            with pytest.raises(OktoNexusError, match='applied dispatch lease'):
                                dispatch(held)
                            with pytest.raises(CoreError):
                                runtime.r4_operation_context(authorized.frame, connection_id=channel.connection_id,
                                    connection_generation=channel.connection_generation)
                            fresh.clear()  # Containment does not need new binary discovery.
                            interrupt = await resolve('turn.interrupt', 'interrupt', target=current_run)
                            assert interrupt.can_submit, interrupt.blockers
                            await http.submit_r4_operation(key, interrupt)
                            stopped = dispatch(reserve())
                            assert stopped.frame['intent_hash'] == interrupt.intent_hash
                            assert 'expected_turn_id' not in stopped.frame
                            contained_context = runtime.r4_operation_context(stopped.frame,
                                connection_id=channel.connection_id, connection_generation=channel.connection_generation)
                            interruption = ControlOperation(interrupt.operation_id, scope['session_id'], 'interrupt',
                                reason=stopped.frame['payload']['reason'])
                            receipt = await runtime.control(interruption, contained_context)
                            assert await runtime.control(interruption, contained_context) == receipt
                            accepted = await http.publish_core_interrupt_receipt(ticket, submit_frame=stopped.frame,
                                core_receipt=receipt, context=contained_context, receipt_revision=1)
                            assert accepted.operation_id == interrupt.operation_id
                            assert native.native.sent == [('steer',steer.operation_id),('interrupt',interrupt.operation_id)]
                            with factory.unit_of_work(write=False) as uow:
                                assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants').fetchone()[0] == 2
                                assert uow.connection.execute("SELECT COUNT(*) FROM execution_client_intents WHERE client_intent_id='invalid'").fetchone()[0] == 0
                            long_reason = await resolve('turn.interrupt', 'long-reason', text='x'*1024, target=current_run)
                            assert long_reason.can_submit and long_reason.semantic_intent['payload']['reason'] == 'x'*1024
                            oversized = await resolve('turn.steer', 'oversized', text='\u00e9'*40000, target=native_target)
                            assert not oversized.can_submit and 'operation_payload_too_large' in oversized.blockers
                            if finish == 'revoke':
                                revoked = await resolve('turn.interrupt', 'revoke-before-send', target=current_run)
                                await http.submit_r4_operation(key, revoked)
                                reserved = reserve()
                                access.revoke(operator, grant_id=canonical['grant_id'])
                                with pytest.raises(OktoNexusError):
                                    dispatch(reserved)
                            else:
                                closing = await resolve('runtime.close', 'close', text='x'*1024)
                                assert closing.can_submit and closing.semantic_intent['target']['kind'] == 'none'
                                await http.submit_r4_operation(key, closing)
                                authorized_close = dispatch(reserve())
                                assert authorized_close.frame['intent_hash'] == closing.intent_hash
                                close_context = runtime.r4_operation_context(authorized_close.frame,
                                    connection_id=channel.connection_id, connection_generation=channel.connection_generation)
                                close_operation = r4_close_operation(authorized_close.frame)
                                close_entered,close_release = asyncio.Event(),asyncio.Event()
                                original_close = native.native.close
                                close_calls = []
                                async def slow_close():
                                    close_calls.append('close')
                                    close_entered.set()
                                    await close_release.wait()
                                    return await original_close()
                                native.native.close = slow_close
                                waiter = asyncio.create_task(runtime.close(close_operation, close_context))
                                try:
                                    await asyncio.wait_for(close_entered.wait(),2)
                                    pending_close = await journal.get_receipt(OperationKey(server, executor, closing.operation_id))
                                    assert pending_close.stage == 'SUBMISSION_STARTED'
                                    await http.publish_core_close_receipt(ticket, submit_frame=authorized_close.frame,
                                        core_receipt=pending_close, context=close_context, receipt_revision=1)
                                    with factory.unit_of_work(write=False) as uow:
                                        assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == 'READY'
                                    waiter.cancel()
                                    with pytest.raises(asyncio.CancelledError): await waiter
                                    replay = asyncio.create_task(runtime.close(close_operation, close_context))
                                    close_release.set()
                                    closed = await asyncio.wait_for(replay,2)
                                finally:
                                    close_release.set()
                                    await asyncio.gather(waiter,return_exceptions=True)
                                assert closed.stage == 'SUCCEEDED' and native.native.stopped
                                assert close_calls == ['close']
                                assert await runtime.close(close_operation, close_context) == closed
                                with factory.unit_of_work() as uow:
                                    uow.connection.execute("CREATE TRIGGER fail_closed BEFORE UPDATE OF lifecycle_state ON execution_sessions WHEN NEW.lifecycle_state='CLOSED' BEGIN SELECT RAISE(ABORT,'close projection fault'); END")
                                from okto_nexus_connector.errors import ConnectorError
                                with pytest.raises(ConnectorError):
                                    await http.publish_core_close_receipt(ticket, submit_frame=authorized_close.frame,
                                        core_receipt=closed, context=close_context, receipt_revision=2)
                                with factory.unit_of_work() as uow:
                                    assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == 'READY'
                                    assert uow.connection.execute('SELECT MAX(receipt_revision) FROM execution_receipts WHERE operation_id=?',(closing.operation_id,)).fetchone()[0] == 1
                                    uow.connection.execute('DROP TRIGGER fail_closed')
                                await http.publish_core_close_receipt(ticket, submit_frame=authorized_close.frame,
                                    core_receipt=closed, context=close_context, receipt_revision=2)
                                repeated = await http.publish_core_close_receipt(ticket, submit_frame=authorized_close.frame,
                                    core_receipt=closed, context=close_context, receipt_revision=2)
                                assert repeated.reused
                                with factory.unit_of_work(write=False) as uow:
                                    assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()) == ('CLOSED','CLOSED')
                                after_close = await resolve('turn.submit','after-close',text='New work')
                                assert not after_close.can_submit and 'session_not_ready' in after_close.blockers
                            assert len(native.native.sent) == 2
                            release_unsent_dispatch(factory, reservation=held)
                finally:
                    await runtime.shutdown(ShutdownPolicy(0,0))
                    await journal.aclose()
            asyncio.run(run())
