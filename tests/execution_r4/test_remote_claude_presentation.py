"""Remote Claude presentation shares the approved owner's canonical queue."""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import pytest
import test_pr34_remediation as tcp
from nexus_connector_core import LocalRuntimeCore, RuntimeEvent
from nexus_connector_core.presentation_link import CLAUDE_PRESENTATION_LINK_REVISION
from remote_renewal_helpers import RemoteProject
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from okto_nexus.adapters.inbound.cli import session as session_cli
from okto_nexus.adapters.inbound.cli.session_commands import recover_session_command
from okto_nexus.adapters.inbound.http import dashboard_session_presentations
from okto_nexus.adapters.outbound.local_presenter_client import open_local_presentation, review_local_presentation
from okto_nexus.application.terminal_connection import PREFIX
from okto_nexus.domain.presentation_protocol import REMOTE_CLAUDE_SUBPROTOCOL


@pytest.mark.parametrize('access', ['read', 'write'])
def test_remote_claude_presentation_expires_and_can_reattach_to_same_owner(tmp_path, monkeypatch, request, access):
    original = tcp.build_app
    apps, readers = [], []

    def app(deps, **kwargs):
        deps.config.runtime_session_interaction_enabled = True
        built = original(deps, **kwargs)
        apps.append(built)
        return built

    monkeypatch.setattr(tcp, 'build_app', app)
    for module in ('availability', 'executor_inventory'):
        monkeypatch.setattr(f'nexus_connector_core.{module}.qualified_build', lambda *_a, **_k: True)
    monkeypatch.setattr('okto_nexus.application.remote_claude_presentation.reviewed_claude_terminal_context',
                        lambda mapping: mapping.adapter_id == 'claude_stream')

    @asynccontextmanager
    async def open_terminal(runtime, scope, target, *, connection_id, connection_generation):
        runtime.r4_native_action_context(scope, connection_id=connection_id, connection_generation=connection_generation)
        native, epoch, _ = project.native.opened[scope['session_id']]
        assert (target.adapter_id, target.native_session_id, target.stream_epoch) == (
            'claude_stream', native.native_id, epoch)

        async def output():
            yield b'One exact Claude terminal'
            await asyncio.Future()

        async with _record_reader(output(), readers) as frames:
            yield frames

    monkeypatch.setattr(LocalRuntimeCore, 'open_live_claude_terminal', open_terminal)
    with pytest.MonkeyPatch.context() as fixture_patch:
        fixture = tcp._runtime(tmp_path, request, fixture_patch)
        runtime = next(fixture)
        project = RemoteProject(runtime, tmp_path, monkeypatch, actions=8, adapter_id='claude_stream')
        project.observed = replace(project.observed, architecture='x86_64')

        async def run():
            try:
                await project.start()
                control = project.control.connection
                assert CLAUDE_PRESENTATION_LINK_REVISION in control.state.control_capabilities
                opened = await asyncio.to_thread(project.work().submit, 'Existing Claude work', new_session=True)
                await project.operation(opened['operation_id'], stage='SUBMITTED')
                operation = opened['submission_turn_operation_id']
                await project.operation(operation, stage='SUBMITTED')
                scope = opened['scope']
                session = scope['session_id']
                native, epoch, _ = project.native.opened[session]
                await native.queue.put(RuntimeEvent(scope['server_id'], scope['executor_id'], session, epoch, 0,
                    'tool_activity', 'fixture.started', {'delivery_phase': 'started'}, operation_id=operation))
                await project.eventually(lambda: any(row['stream_epoch'] == epoch
                                                    for row in project.rows('execution_sessions')))
                exact = {key: scope[key] for key in ('server_id', 'executor_id', 'binding_id', 'workspace_id',
                                                     'workspace_binding_id', 'agent_id', 'session_id')}
                generation = scope['session_owner_generation']
                document = {'scope': exact, 'expected_session_generation': generation, 'presentation': 'claude_remote'}
                path = PREFIX + f'/sessions/{session}/attachments:'
                headers = project.http.request_headers()
                async with httpx.AsyncClient(base_url=project.origin) as http:
                    assert (await http.post(path + 'review', json=document | {
                        'access': 'write', 'expected_session_generation': generation + 1}, headers=headers)).status_code == 409
                    assert (await http.post(path + 'review', json=document,
                        headers=headers | {'Origin': 'https://foreign.invalid'})).status_code == 403
                    assert (await http.post(path + 'review', json=document, headers={
                        'Authorization': 'Bearer ' + project.key, 'Origin': project.origin,
                        'X-Nexus-UI': '1', 'X-Nexus-Operator-Session-Required': '1'})).status_code in (401, 403)
                assert not readers

                broker = apps[0].state.remote_claude_presentations.broker
                clock = [time.monotonic()]
                monkeypatch.setattr(broker, 'clock', lambda: clock[0])
                monkeypatch.setattr(dashboard_session_presentations, '_RENEW_SECONDS', 0)
                require_active = broker.require_active
                checks = []

                def observe_active(**kwargs):
                    current = clock[0]
                    result = require_active(**kwargs)
                    checks.append(current)
                    return result

                monkeypatch.setattr(broker, 'require_active', observe_active)
                attachment = document | {'access': access}
                reviewed = await asyncio.to_thread(project.http, 'POST', path + 'review', attachment)
                writer = {'expected_writer_epoch': reviewed['writer_epoch']} if access == 'write' else {}
                offer = await asyncio.to_thread(project.http, 'POST', path + 'prepare', attachment | writer | {
                    'intent': 'attach_live', 'client_intent_id': 'silent-claude',
                    'capability_revision': reviewed['capability_revision']})
                assert offer['claude_keepalive'] is True
                uri = project.origin.replace('http://', 'ws://', 1) + PREFIX + f"/attachments/{offer['attachment_id']}/stream"
                old_intent = 'claude_input_' + 'b' * 32
                queued_before_expiry = None
                async with connect(uri, subprotocols=[REMOTE_CLAUDE_SUBPROTOCOL], origin=project.origin,
                        additional_headers={'Authorization': 'Bearer ' + offer['ticket'], 'Cookie': headers['Cookie']}) as wire:
                    await wire.send(json.dumps({'kind': 'hello', 'version': 1, 'scope': exact,
                                                'expected_session_generation': generation}))
                    challenge = json.loads(await asyncio.wait_for(wire.recv(), 8))
                    await wire.send(json.dumps({'kind': 'prove', 'challenge': challenge['challenge']}))
                    assert json.loads(await asyncio.wait_for(wire.recv(), 8))['access'] == access
                    assert await asyncio.wait_for(wire.recv(), 8) == b'One exact Claude terminal'
                    if access == 'write':
                        await wire.send(json.dumps({
                            'kind': 'enqueue', 'request_id': 1, 'client_intent_id': old_intent,
                            'capability_revision': reviewed['input_capability_revision'],
                            'content': {'type': 'text', 'text': 'Queue this before the viewer goes silent'},
                        }))
                        queued_before_expiry = json.loads(await asyncio.wait_for(wire.recv(), 8))
                        assert queued_before_expiry['request_id'] == 1
                        assert queued_before_expiry['status'] == 'QUEUED' and queued_before_expiry['operation_id'] is None

                    def expires():
                        return project.rows('session_attachments')[0]['expires_monotonic']

                    first_expiry = expires()
                    clock[0] += 10
                    await wire.send(json.dumps({'kind': 'keepalive'}))
                    await project.eventually(lambda: expires() > first_expiry)
                    expiry = expires()
                    clock[0] += 10
                    await asyncio.wait_for(await wire.ping(), 5)
                    await project.eventually(lambda: clock[0] in checks)
                    assert expires() == expiry
                    clock[0] = expiry + 1
                    with pytest.raises(ConnectionClosed):
                        await asyncio.wait_for(wire.recv(), 8)
                await project.eventually(lambda: project.rows('session_attachments')[0]['state'] == 'DETACHED')
                binding = await asyncio.to_thread(project.work().binding)

                def read(link):
                    assert link.read_terminal_output() == b'One exact Claude terminal'

                monkeypatch.setattr(session_cli, '_show_claude_transcript', read)
                attachment = await asyncio.to_thread(session_cli.attach_session, project.http, binding,
                                                       session_id=session, interactive=True)
                assert attachment['attach_strategy'] == 'claude_remote_read' and attachment['scope'] == exact
                await project.eventually(lambda: all(row['state'] == 'DETACHED'
                                                     for row in project.rows('session_attachments')))
                assert all(reader == 'detached' for reader in readers)
                assert control.online and not native.stopped and native.sent == [('send_turn', operation)]
                assert len(project.rows('execution_operations')) == 2
                if queued_before_expiry is None:
                    assert not project.rows('session_interaction_inputs')
                else:
                    original = await asyncio.to_thread(recover_session_command, project.http, binding, session,
                                                       generation, old_intent)
                    assert original['receipt']['input_id'] == queued_before_expiry['input_id']
                    assert original['receipt']['status'] == 'QUEUED' and original['receipt']['operation_id'] is None

                intent = 'claude_input_' + 'c' * 32

                def enqueue():
                    writer = review_local_presentation(project.http, scope=exact, expected_session_generation=generation,
                        write=True, presentation='claude_remote')
                    assert writer.occupied is False
                    with open_local_presentation(project.http, scope=exact, expected_session_generation=generation,
                            capability_revision=writer.capability_revision, client_intent_id='remote-claude-writer',
                            writer=writer, claude=True, remote=True) as link:
                        assert link.read_terminal_output() == b'One exact Claude terminal'
                        return link.send_terminal_input(intent=intent, text='Queue this after the active turn',
                                                        output=lambda _: None)

                queued = await asyncio.to_thread(enqueue)
                assert queued['status'] == 'QUEUED' and queued['operation_id'] is None
                recovered = await asyncio.to_thread(recover_session_command, project.http, binding, session, generation, intent)
                assert recovered['receipt']['input_id'] == queued['input_id']
                assert recovered['receipt']['status'] == 'QUEUED'
                await project.eventually(lambda: all(row['state'] == 'DETACHED'
                                                     for row in project.rows('session_attachments')))
                assert all(reader == 'detached' for reader in readers)
                assert control.online and not native.stopped and native.sent == [('send_turn', operation)]
                assert len(project.rows('execution_operations')) == 2
                stored = sorted(project.rows('session_interaction_inputs'), key=lambda row: row['enqueue_sequence'])
                expected_ids = [queued['input_id']]
                if queued_before_expiry is not None:
                    expected_ids.insert(0, queued_before_expiry['input_id'])
                assert [row['input_id'] for row in stored] == expected_ids
                assert all(row['surface'] == 'native_terminal' and row['session_id'] == session for row in stored)
            finally:
                await project.close()

        try:
            asyncio.run(run())
        finally:
            fixture.close()


@asynccontextmanager
async def _record_reader(frames, readers):
    index = len(readers)
    readers.append('open')
    try:
        yield frames
    finally:
        await frames.aclose()
        readers[index] = 'detached'
