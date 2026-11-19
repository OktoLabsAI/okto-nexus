"""Real HTTP/Connector WebSocket and canonical lease with a synthetic Codex read."""

import asyncio
import time
from dataclasses import asdict, replace

import httpx
import pytest
import test_pr34_remediation as tcp
from fastapi import Request
from fastapi.responses import JSONResponse
from nexus_connector_core import CoreError, LocalRuntimeCore, RuntimeEvent
from nexus_connector_core.presentation_link import (
    PRESENTATION_LINK_REVISION,
    decode_presentation_frame,
    presentation_result,
)
from nexus_connector_core.protocol import canonical_json
from remote_renewal_helpers import RemoteProject
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from okto_nexus.adapters.inbound.cli import session as session_cli
from okto_nexus.adapters.inbound.cli.session_commands import recover_session_command
from okto_nexus.adapters.inbound.http.operator_auth import COOKIE
from okto_nexus.adapters.outbound.execution.presentation_link import PresentationLink
from okto_nexus.adapters.outbound.local_presenter_client import _LocalPresenter
from okto_nexus.application.codex_viewer_protocol import CodexInputStatus
from okto_nexus.application.execution_leases import ExecutionChannel
from okto_nexus.application.terminal_connection import PREFIX, ConnectionError
from okto_nexus.domain.execution.keys import SessionKey, SessionOwnerGeneration
from okto_nexus.domain.presentation_protocol import REMOTE_CODEX_SUBPROTOCOL
from okto_nexus.domain.session_interaction import InputAuthor, InputScope

_THREAD = 'bdfe5b81-54cf-43cf-8001-5de670d3dd69'
_TURN = '3ef9bcae-c51a-4d6a-ae90-d7648356532e'
_ROUTE = '/api/v1/__fixture_remote_presentation'


def test_link_rejects_misbound_reply_and_discards_late_reply_after_disconnect():
    async def run():
        frames = asyncio.Queue()

        async def send(raw):
            await frames.put(decode_presentation_frame(raw.encode('utf-8')))

        channel = ExecutionChannel('server', 'executor', 'connection', 1)
        link = PresentationLink(channel, send)
        selected = {'server_id': 'server', 'executor_id': 'executor', 'binding_id': 'binding', 'agent_id': 'agent',
            'workspace_id': 'workspace', 'workspace_binding_id': 'workspace-binding', 'session_id': 'session',
            'session_owner_generation': 1, 'binding_revision': 1, 'credential_epoch': 1,
            'authorization_revision': 2, 'configuration_revision': 3}
        target = {'adapter_id': 'codex_app_server', 'opening_operation_id': 'opening',
                      'native_session_id': 'owned', 'stream_epoch': 'stream'}
        read = asyncio.create_task(link.read_codex(scope=selected, target=target, thread_id=_THREAD))
        frame = await asyncio.wait_for(frames.get(), 2)
        reply = presentation_result(frame, None)
        for mismatch in (reply | {'request_hash': 'sha256:' + 'f' * 64},
                         reply | {'connection_generation': 2}):
            with pytest.raises(CoreError) as error:
                link.accept_result(mismatch)
            assert error.value.code == 'SCOPE_MISMATCH'
        assert not read.done()
        link.disconnect()
        with pytest.raises(CoreError):
            await asyncio.wait_for(read, 2)
        link.accept_result(reply)
        assert frames.empty()

    asyncio.run(run())


@pytest.mark.parametrize('mode', ['logout-inflight', 'terminal-reattach', 'writer'])
def test_exact_remote_codex_context_authority_and_terminal_reattach(tmp_path, monkeypatch, request, mode):
    original_app = tcp.build_app
    reads = []
    entered, release = asyncio.Event(), asyncio.Event()

    def build_app(deps, **kwargs):
        deps.config.runtime_session_interaction_enabled = True
        app = original_app(deps, **kwargs)

        @app.post(_ROUTE)
        async def read_context(request: Request):
            token = request.cookies.get(COOKIE)
            ref = await asyncio.to_thread(app.state.operator_auth.authority_reference, token=token)
            if ref is None:
                return JSONResponse({}, status_code=401)
            data = await request.json()
            scope = InputScope(SessionKey(data['server_id'], data['executor_id'], data['session_id']),
                SessionOwnerGeneration(data['session_owner_generation']), data['binding_id'],
                data['workspace_id'], data['workspace_binding_id'], data['agent_id'])
            try:
                selected, context = await app.state.remote_codex_presentation.read(
                    scope, InputAuthor(ref, 'native_terminal'))
            except CoreError:
                return JSONResponse({}, status_code=409)
            return {'opening': selected.opening_operation_id, 'context': context.model_dump()}

        return app

    monkeypatch.setattr(tcp, 'build_app', build_app)
    # The synthetic inventory candidate cannot satisfy the production binary
    # fingerprint. Keep the retained thread and all authority checks real.
    monkeypatch.setattr('okto_nexus.application.remote_codex_presentation.reviewed_codex_context',
                        lambda context: context.codex_thread_id == _THREAD)

    async def peer(runtime, scope, target, thread_id, *, connection_id, connection_generation):
        runtime.r4_native_action_context(scope, connection_id=connection_id,
                                         connection_generation=connection_generation)
        assert target.adapter_id == 'codex_app_server' and thread_id == _THREAD
        assert scope['session_id'] in project.native.opened
        native, epoch, cwd = project.native.opened[scope['session_id']]
        assert target.native_session_id == native.native_id and target.stream_epoch == epoch
        reads.append((scope, asdict(target)))
        if mode == 'logout-inflight' and len(reads) == 2:
            entered.set()
            await release.wait()
        completed = any('turn/completed' in row['payload_json'] for row in project.rows('execution_event_ingress'))
        return {'viewer_context': {'thread_id': thread_id, 'session_id': 'native-viewer-synthetic', 'cwd': cwd,
            'model': 'synthetic', 'model_provider': 'fixture', 'status': 'idle' if completed else 'active', 'created_at': 1,
            'updated_at': 2, 'ephemeral': False, 'cli_version': '0.157.0', 'source': 'cli',
            'approval_policy': 'on-request', 'approvals_reviewer': 'user', 'sandbox': {'type': 'readOnly'},
            'reasoning_effort': 'medium'}}

    monkeypatch.setattr(LocalRuntimeCore, 'read_live_codex_thread', peer)
    with pytest.MonkeyPatch.context() as fixture_patch:
        fixture = tcp._runtime(tmp_path, request, fixture_patch)
        runtime = next(fixture)
        writing = mode == 'writer'
        project = RemoteProject(runtime, tmp_path, monkeypatch, actions=8 if writing else 1)
        if writing:
            project.observed = replace(project.observed, architecture='x86_64')
            for module in ('availability', 'executor_inventory'):
                monkeypatch.setattr(f'nexus_connector_core.{module}.qualified_build', lambda *_args, **_kwargs: True)

        async def run():
            try:
                await project.start()
                connection = project.control.connection
                assert PRESENTATION_LINK_REVISION in connection.state.control_capabilities
                opened = await asyncio.to_thread(project.work().submit, 'Synthetic ongoing work', new_session=True,
                                                 client_intent_id='remote-reader-open')
                await project.operation(opened['operation_id'], stage='SUBMITTED')
                child = opened['submission_turn_operation_id']
                await project.operation(child, stage='SUBMITTED')
                scope = opened['scope']
                session = scope['session_id']
                native, epoch, cwd = project.native.opened[session]
                await native.queue.put(RuntimeEvent(project.server_id, scope['executor_id'], session, epoch, 0,
                    'lifecycle', 'core/codex_thread_configuration', {'schema_version': 1,
                    'adapter_id': 'codex_app_server', 'source': 'thread/start/response', 'thread_id': _THREAD}))
                await project.eventually(lambda: any('core/codex_thread_configuration' in row['payload_json']
                    for row in project.rows('execution_event_ingress')))
                if mode in ('terminal-reattach', 'writer'):
                    attach = _run_remote_writer if writing else _run_terminal_reattach
                    await attach(project, scope, child, native, epoch, cwd, monkeypatch)
                    assert connection.online and not native.stopped and len(project.native.opened) == 1
                    assert reads and all(target['opening_operation_id'] == opened['operation_id'] for _, target in reads)
                    return
                before = project.rows('execution_operations')
                async with httpx.AsyncClient(base_url=project.origin, timeout=8) as client:
                    agent = {'Authorization': 'Bearer ' + project.key}
                    assert (await client.post(_ROUTE, headers=agent, json=scope)).status_code in (401, 403)
                    assert reads == []
                    headers = project.http.request_headers()
                    stale = scope | {'session_owner_generation': scope['session_owner_generation'] + 1}
                    assert (await client.post(_ROUTE, headers=headers, json=stale)).status_code == 409
                    assert reads == []
                    result = await client.post(_ROUTE, headers=headers, json=scope)
                    assert result.status_code == 200, result.text
                    assert result.json()['context']['cwd'] == cwd == str(project.project)
                    assert result.json()['opening'] == opened['operation_id']

                    pending = asyncio.create_task(client.post(_ROUTE, headers=headers, json=scope))
                    try:
                        await asyncio.wait_for(entered.wait(), 5)
                        auth = project.profile.client()
                        await asyncio.to_thread(auth, 'POST', '/api/v1/operator-auth/logout')
                    finally:
                        release.set()
                    refused = await pending
                    assert refused.status_code == 409 and refused.json() == {}
                assert connection.online and not native.stopped and len(project.native.opened) == 1
                assert len(reads) == 2
                assert project.rows('execution_operations') == before
                await native.queue.put(RuntimeEvent(project.server_id, scope['executor_id'], session, epoch, 0,
                    'turn_state', 'fixture.finished', {'delivery_phase': 'terminal', 'delivery_outcome': 'success'},
                    operation_id=child))
                async with httpx.AsyncClient(base_url=project.origin) as client:
                    async def completed():
                        while True:
                            result = await client.get('/v1/runtime/operations/' + child, headers=agent)
                            if result.json().get('executor_stage') == 'SUCCEEDED':
                                return
                            await asyncio.sleep(.05)
                    await asyncio.wait_for(completed(), 8)
            finally:
                await project.close()

        try:
            asyncio.run(run())
        finally:
            fixture.close()


async def _run_terminal_reattach(project, scope, operation_id, native, epoch, cwd, monkeypatch):
    session_id = scope['session_id']
    server_id, executor_id = scope['server_id'], scope['executor_id']
    exact = {key: scope[key] for key in ('server_id', 'executor_id', 'binding_id', 'workspace_id',
                                        'workspace_binding_id', 'agent_id', 'session_id')}
    document = {'scope': exact, 'expected_session_generation': scope['session_owner_generation']}
    turn_scope = {'threadId': _THREAD, 'thread_id': _THREAD, 'turnId': _TURN, 'turn_id': _TURN}

    async def emit(category, method, payload):
        await native.queue.put(RuntimeEvent(server_id, executor_id, session_id, epoch, 0, category, method,
                                            turn_scope | payload, operation_id=operation_id))

    await emit('turn_state', 'turn/started', {'delivery_phase': 'started', 'turn': {'id': _TURN, 'status': 'inProgress'}})
    await project.eventually(lambda: any('turn/started' in row['payload_json']
        for row in project.rows('execution_event_ingress')))
    attach_path = PREFIX + f'/sessions/{session_id}/attachments:'
    async with httpx.AsyncClient(base_url=project.origin) as wire:
        headers = project.http.request_headers()
        review = document | {'presentation': 'codex_remote'}
        foreign = await wire.post(attach_path + 'review', json=review, headers=headers | {'Origin': 'https://other.invalid'})
        assert foreign.status_code == 403
        agent = await wire.post(attach_path + 'review', json=review, headers={
            'Origin': project.origin, 'X-Nexus-UI': '1', 'X-Nexus-Operator-Session-Required': '1',
            'Authorization': 'Bearer ' + project.key})
        assert agent.status_code in (401, 403)
        assert project.rows('session_attachments') == []

    loop = asyncio.get_running_loop()
    binding = await asyncio.to_thread(project.work().binding)
    before = {row['operation_id'] for row in project.rows('execution_operations')}
    offers, viewers = [], []

    def api(method, path, body=None):
        result = project.http(method, path, body)
        if path == attach_path + 'prepare':
            offers.append(result)
        return result

    for name in ('base', 'token', 'server_id', 'request_headers'):
        setattr(api, name, getattr(project.http, name))

    async def finish():
        await emit('tool_activity', 'item/completed', {'item': {'type': 'agentMessage',
            'id': 'remote-result', 'text': 'Finished on the Connector'}})
        await emit('turn_state', 'turn/completed', {'delivery_phase': 'terminal', 'delivery_outcome': 'success',
            'turn': {'id': _TURN, 'status': 'completed'}, 'output_text': 'Finished on the Connector'})

    def viewer(link, executable):
        assert executable == 'fixture-reviewed-viewer' and link.input_revision is None and link.live_updates
        context = link.viewer_context()
        assert context.thread_id == _THREAD and context.cwd == cwd == str(project.project)
        page = link.page(method='thread/turns/list', params={'threadId': _THREAD})
        assert page['data'][0]['id'] == _TURN and page['data'][0]['status'] == 'inProgress'
        if not viewers:
            viewers.append((link.attachment_id, page['backwardsCursor']))
            link.close()
            return
        asyncio.run_coroutine_threadsafe(finish(), loop).result(timeout=5)
        notices = []
        deadline = time.monotonic() + 8
        while not any(item['method'] == 'turn/completed' for item in notices):
            assert time.monotonic() < deadline
            notices.extend(link.updates(_THREAD))
            time.sleep(.05)
        assert any(item['params'].get('item', {}).get('text') == 'Finished on the Connector' for item in notices)
        with pytest.raises(ConnectionError):
            link.page(method='thread/turns/list', params={
                'threadId': _THREAD, 'cursor': viewers[0][1], 'sortDirection': 'asc'})
        viewers.append((link.attachment_id, page['backwardsCursor']))

    monkeypatch.setattr(session_cli, 'select_viewer', lambda _: 'fixture-reviewed-viewer')
    monkeypatch.setattr(session_cli, 'present_codex', viewer)
    with pytest.raises(ConnectionError) as refusal:
        await asyncio.to_thread(session_cli.attach_session, api, binding, session_id=session_id,
                                interactive=True, write=True)
    assert refusal.value.http_status == 409
    first = await asyncio.to_thread(session_cli.attach_session, api, binding, session_id=session_id, interactive=True)
    assert first['attach_strategy'] == 'codex_remote_read'
    await project.eventually(lambda: [row['state'] for row in project.rows('session_attachments')] == ['DETACHED'])
    assert not native.stopped and native.sent == [('send_turn', operation_id)]

    offer, = offers
    socket_path = PREFIX + f"/attachments/{offer['attachment_id']}/stream"
    async with connect(project.origin.replace('http://', 'ws://', 1) + socket_path,
            subprotocols=[REMOTE_CODEX_SUBPROTOCOL], origin=project.origin,
            additional_headers={'Authorization': 'Bearer ' + offer['ticket'], 'Cookie': headers['Cookie']}) as socket:
        await socket.send(canonical_json({'kind': 'hello', 'version': 1, **document}).decode())
        with pytest.raises(ConnectionClosed):
            await socket.recv()

    second = await asyncio.to_thread(session_cli.attach_session, api, binding, session_id=session_id, interactive=True)
    assert second['attachment_id'] != first['attachment_id'] and second['scope'] == first['scope'] == exact
    assert len(viewers) == 2 and viewers[0][1] != viewers[1][1]
    await project.operation(operation_id)
    await project.eventually(lambda: sorted(row['state'] for row in project.rows('session_attachments')) ==
                             ['DETACHED', 'DETACHED'])

    def completed_viewer(link, executable):
        context = link.viewer_context()
        assert context.thread_id == _THREAD and context.status == 'idle' and context.cwd == cwd
        page = link.page(method='thread/turns/list', params={'threadId': _THREAD})
        assert page['data'][0]['id'] == _TURN and page['data'][0]['status'] == 'completed'

    monkeypatch.setattr(session_cli, 'present_codex', completed_viewer)
    third = await asyncio.to_thread(session_cli.attach_session, api, binding, session_id=session_id, interactive=True)
    assert third['scope'] == exact and len({first['attachment_id'], second['attachment_id'], third['attachment_id']}) == 3
    await project.eventually(lambda: [row['state'] for row in project.rows('session_attachments')] == ['DETACHED'] * 3)
    assert {row['operation_id'] for row in project.rows('execution_operations')} == before
    assert not native.stopped and native.sent == [('send_turn', operation_id)]


async def _run_remote_writer(project, scope, operation_id, native, epoch, cwd, monkeypatch):
    session = scope['session_id']
    turn = {'threadId': _THREAD, 'thread_id': _THREAD, 'turnId': _TURN, 'turn_id': _TURN}
    native.active_turn_id = _TURN
    await native.queue.put(RuntimeEvent(scope['server_id'], scope['executor_id'], session, epoch, 0,
        'turn_state', 'turn/started', turn | {'delivery_phase': 'started', 'turn': {'id': _TURN, 'status': 'inProgress'}},
        operation_id=operation_id))
    await project.eventually(lambda: any('turn/started' in row['payload_json']
        for row in project.rows('execution_event_ingress')))
    generation = scope['session_owner_generation']
    binding = await asyncio.to_thread(project.work().binding)
    intent = 'codex_b37538e5-0f91-49f3-8420-cf451ffe21e0'
    exchange = _LocalPresenter.exchange

    def lose_enqueue_reply(link, frame, **options):
        result = exchange(link, frame, **options)
        if frame['kind'] == 'enqueue':
            assert result['status'] == 'QUEUED'
            link.close()
            raise ConnectionError('OUTCOME_UNKNOWN', 'Fixture lost the acknowledgement.', possible_effect=True)
        return result

    def viewer(link, executable):
        assert link.input_revision and link.viewer_context().cwd == cwd
        pending = link.send_next_turn(thread_id=_THREAD, intent=intent, text='One durable message')
        assert pending.input_id is None and 'unconfirmed' in pending.message

    monkeypatch.setattr(_LocalPresenter, 'exchange', lose_enqueue_reply)
    monkeypatch.setattr(session_cli, 'select_viewer', lambda _: 'fixture-reviewed-viewer')
    monkeypatch.setattr(session_cli, 'present_codex', viewer)
    first = await asyncio.to_thread(session_cli.attach_session, project.http, binding, session_id=session,
                                   interactive=True, write=True)
    assert first['attach_strategy'] == 'codex_remote_write'
    await project.eventually(lambda: [row['state'] for row in project.rows('session_attachments')] == ['DETACHED'])
    receipt = await asyncio.to_thread(recover_session_command, project.http, binding, session, generation, intent)
    assert receipt['receipt']['status'] == 'QUEUED'
    assert len(project.rows('session_interaction_inputs')) == 1
    assert native.sent == [('send_turn', operation_id)] and not native.stopped

    cancelled = 'codex_interrupt_' + 'a' * 32
    interrupted = 'codex_interrupt_' + 'b' * 32
    steered = 'codex_steer_516a78af-4028-424e-91d3-2c9d42fd8d3d'
    reorientations = []
    controls = []
    send = native.send

    async def record_send(verb, payload, operation, *, expected_turn_id=None):
        if verb == 'steer':
            reorientations.append((expected_turn_id, payload['text']))
        if verb == 'interrupt':
            controls.append((expected_turn_id, project.rows('session_interaction_queues')[0]['paused_owner_generation']))
        return await send(verb, payload, operation, expected_turn_id=expected_turn_id)

    native.send = record_send

    def steer(link, executable):
        assert link.viewer_context().thread_id == _THREAD
        pending = link.steer(thread_id=_THREAD, turn_id=_TURN, intent=steered, text='Refine the active turn',
                             confirm=lambda target, text: (target, text) == (_TURN, 'Refine the active turn'))
        assert pending.input_id and pending.steer_target == _TURN

    monkeypatch.setattr(session_cli, 'present_codex', steer)
    second = await asyncio.to_thread(session_cli.attach_session, project.http, binding, session_id=session,
                                    interactive=True, write=True)
    assert second['attachment_id'] != first['attachment_id']
    await project.eventually(lambda: reorientations == [(_TURN, 'Refine the active turn')])
    receipt = await asyncio.to_thread(recover_session_command, project.http, binding, session, generation, steered)
    assert receipt['command'] == 'steer' and receipt['receipt']['reorientation'] is True

    def interrupt(link, executable):
        assert link.viewer_context().thread_id == _THREAD
        with pytest.raises(CodexInputStatus, match='unavailable'):
            link.interrupt(thread_id=_THREAD, turn_id=_THREAD, intent=cancelled, confirm=lambda _: pytest.fail('Wrong turn'))
        with pytest.raises(CodexInputStatus, match='cancelled'):
            link.interrupt(thread_id=_THREAD, turn_id=_TURN, intent=cancelled, confirm=lambda _: False)
        link.interrupt(thread_id=_THREAD, turn_id=_TURN, intent=interrupted, confirm=lambda target: target == _TURN)

    monkeypatch.setattr(session_cli, 'present_codex', interrupt)
    third = await asyncio.to_thread(session_cli.attach_session, project.http, binding, session_id=session,
                                    interactive=True, write=True)
    assert len({first['attachment_id'], second['attachment_id'], third['attachment_id']}) == 3
    await project.eventually(lambda: controls == [(_TURN, generation)])
    receipt = await asyncio.to_thread(recover_session_command, project.http, binding, session, generation, interrupted)
    assert receipt['receipt']['interrupt']['queue_paused'] is True
    inputs = project.rows('session_interaction_inputs')
    assert len(inputs) == 2 and any(row['status'] == 'QUEUED' for row in inputs) and not native.stopped
