"""The Pi terminal uses the real Nexus and Connector links with a fixture renderer."""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
import test_pr34_remediation as tcp
from nexus_connector_core import LocalRuntimeCore, RuntimeEvent
from nexus_connector_core.native.pi_renderer import PiEditorUpdate
from nexus_connector_core.presentation_link import PI_PRESENTATION_LINK_REVISION
from nexus_connector_core.protocol import canonical_json
from nexus_connector_core.turn_operation import PI_LITERAL_INPUT_REVISION
from remote_renewal_helpers import RemoteProject
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from okto_nexus.adapters.inbound.cli import session as session_cli
from okto_nexus.adapters.inbound.cli.session_commands import recover_session_command
from okto_nexus.adapters.inbound.http import dashboard_session_presentations
from okto_nexus.adapters.outbound import local_presenter_client
from okto_nexus.application.terminal_connection import PREFIX
from okto_nexus.domain.presentation_protocol import REMOTE_PI_SUBPROTOCOL


@pytest.mark.parametrize('silent', [None, 'read', 'write'])
def test_remote_pi_viewer_and_editor_keep_the_connector_owner_and_queue(tmp_path, monkeypatch, request, silent):
    original = tcp.build_app
    calls, apps = [], []

    def app(deps, **kwargs):
        deps.config.runtime_session_interaction_enabled = True
        built = original(deps, **kwargs)
        apps.append(built)
        return built

    monkeypatch.setattr(tcp, 'build_app', app)
    monkeypatch.setattr('okto_nexus.application.remote_pi_presentation.reviewed_pi_context',
                        lambda mapping: mapping.adapter_id == 'pi_rpc')
    for module in ('availability', 'executor_inventory'):
        monkeypatch.setattr(f'nexus_connector_core.{module}.qualified_build', lambda *_args, **_kwargs: True)

    async def prove(runtime, scope, target, *, connection_id, connection_generation):
        runtime.r4_native_action_context(scope, connection_id=connection_id, connection_generation=connection_generation)
        native, epoch, cwd = project.native.opened[scope['session_id']]
        assert (target.adapter_id, target.native_session_id, target.stream_epoch) == ('pi_rpc', native.native_id, epoch)
        assert cwd == str(project.project)
        calls.append('proof')

    @asynccontextmanager
    async def open_reader(runtime, scope, target, *, columns, rows, **connection):
        await prove(runtime, scope, target, **connection)
        calls.append('reader')

        async def output():
            yield b'One exact Pi transcript'
            await asyncio.Future()

        try:
            yield output()
        finally:
            calls.append('reader-detached')

    @asynccontextmanager
    async def open_editor(runtime, scope, target, *, columns, rows, **connection):
        await prove(runtime, scope, target, **connection)
        calls.append('editor')
        output = asyncio.Queue()
        output.put_nowait(b'One exact Pi editor')
        draft = ''
        sequence = 0

        class Editor:
            async def read_event(self):
                return await output.get()

            async def edit(self, key, *, text):
                nonlocal sequence, draft
                calls.append(key)
                sequence += 1
                if key == 'insert':
                    draft += text
                await output.put(PiEditorUpdate(sequence, draft if key == 'enter' else None))

        try:
            yield Editor()
        finally:
            calls.append('editor-detached')

    monkeypatch.setattr(LocalRuntimeCore, 'prove_live_pi_renderer', prove)
    monkeypatch.setattr(LocalRuntimeCore, 'open_live_pi_renderer', open_reader)
    monkeypatch.setattr(LocalRuntimeCore, 'open_live_pi_editor', open_editor)
    with pytest.MonkeyPatch.context() as fixture_patch:
        fixture = tcp._runtime(tmp_path, request, fixture_patch)
        runtime = next(fixture)
        project = RemoteProject(runtime, tmp_path, monkeypatch, actions=8, adapter_id='pi_rpc')
        project.observed = replace(project.observed, architecture='x86_64')

        async def run():
            try:
                await project.start()
                connection = project.control.connection
                assert PI_PRESENTATION_LINK_REVISION in connection.state.control_capabilities
                assert PI_LITERAL_INPUT_REVISION in connection.state.control_capabilities
                opened = await asyncio.to_thread(project.work().submit, 'Pi work already running', new_session=True,
                                                 client_intent_id='remote-pi-open')
                await project.operation(opened['operation_id'], stage='SUBMITTED')
                operation = opened['submission_turn_operation_id']
                await project.operation(operation, stage='SUBMITTED')
                scope = opened['scope']
                session = scope['session_id']
                binding = await asyncio.to_thread(project.work().binding)
                before = {row['operation_id'] for row in project.rows('execution_operations')}
                native, epoch, _ = project.native.opened[session]
                await native.queue.put(RuntimeEvent(scope['server_id'], scope['executor_id'], session, epoch, 0,
                    'tool_activity', 'agent_start', {'delivery_phase': 'started'}, operation_id=operation))
                await project.eventually(lambda: any(row['stream_epoch'] == epoch for row in project.rows('execution_sessions')))
                exact = {key: scope[key] for key in ('server_id', 'executor_id', 'binding_id', 'workspace_id',
                                                     'workspace_binding_id', 'agent_id', 'session_id')}
                generation = scope['session_owner_generation']
                document = {'scope': exact, 'expected_session_generation': generation, 'presentation': 'pi_remote'}
                url = PREFIX + f'/sessions/{session}/attachments:review'
                async with httpx.AsyncClient(base_url=project.origin) as http:
                    headers = project.http.request_headers()
                    assert (await http.post(url, json=document, headers=headers | {'Origin': 'https://foreign.invalid'})).status_code == 403
                    agent = {'Authorization': 'Bearer ' + project.key, 'Origin': project.origin,
                             'X-Nexus-UI': '1', 'X-Nexus-Operator-Session-Required': '1'}
                    assert (await http.post(url, json=document, headers=agent)).status_code in (401, 403)
                    stale = document | {'expected_session_generation': generation + 1}
                    assert (await http.post(url, json=stale, headers=headers)).status_code == 409
                assert not calls

                if silent is not None:
                    broker = apps[0].state.remote_pi_presentations.broker
                    clock = [time.monotonic()]
                    monkeypatch.setattr(broker, 'clock', lambda: clock[0])
                    monkeypatch.setattr(dashboard_session_presentations, '_RENEW_SECONDS', .05)
                    await _expire_silent_pi(project, document, silent, broker, clock, monkeypatch)
                    monkeypatch.setattr(local_presenter_client, '_PI_KEEPALIVE_SECONDS', .05)
                    assert {row['operation_id'] for row in project.rows('execution_operations')} == before
                    assert connection.online and not native.stopped and native.sent == [('send_turn', operation)]
                    calls.clear()

                def verify_keepalive(link):
                    def expiry():
                        return next(row['expires_monotonic'] for row in project.rows('session_attachments')
                                    if row['attachment_id'] == link.attachment_id)

                    original = expiry()
                    clock[0] += 10
                    deadline = time.monotonic() + 5
                    while expiry() == original:
                        assert time.monotonic() < deadline, 'An idle Pi viewer did not renew its presentation'
                        assert link.poll_pi_output(.1) is None

                def read(link):
                    assert link.input_revision is None and link.read_pi_output() == b'One exact Pi transcript'
                    if silent is not None:
                        verify_keepalive(link)

                monkeypatch.setattr(session_cli, '_show_pi_transcript', read)
                first = await asyncio.to_thread(session_cli.attach_session, project.http, binding,
                                                session_id=session, interactive=True)
                assert first['attach_strategy'] == 'pi_remote_read' and first['scope'] == exact
                await project.eventually(lambda: 'reader-detached' in calls)

                intent = 'pi_input_' + 'd' * 32

                def write(link, recover):
                    assert link.read_pi_output() == b'One exact Pi editor'
                    if silent is not None:
                        verify_keepalive(link)
                    assert link.edit_pi_input(intent=intent, key='insert', text='One durable draft',
                                              output=lambda _: None) == (False, None)
                    assert not project.rows('session_interaction_inputs')
                    assert link.review_pi_control(action='interrupt', intent='pi_interrupt_' + 'b' * 32,
                                                  output=lambda _: None) is None
                    limited, queued = link.edit_pi_input(intent=intent, key='enter', text=None, output=lambda _: None)
                    assert limited is False and queued['status'] == 'QUEUED'

                monkeypatch.setattr(session_cli, 'show_pi_editor', write)
                # Exercise the Windows editor branch with the fixture console on every CI host.
                monkeypatch.setattr(session_cli, 'sys', SimpleNamespace(platform='win32'))
                second = await asyncio.to_thread(session_cli.attach_session, project.http, binding,
                                                 session_id=session, interactive=True, write=True)
                assert second['attach_strategy'] == 'pi_remote_write' and second['scope'] == exact
                await project.eventually(lambda: 'editor-detached' in calls)
                receipt = await asyncio.to_thread(recover_session_command, project.http, binding, session, generation, intent)
                assert receipt['receipt']['status'] == 'QUEUED' and len(project.rows('session_interaction_inputs')) == 1
                assert all(not row['takeover'] for row in project.rows('session_attachments'))
                assert calls.count('enter') == 1 and {row['operation_id'] for row in project.rows('execution_operations')} == before
                assert connection.online and not native.stopped and native.sent == [('send_turn', operation)]
            finally:
                await project.close()

        try:
            asyncio.run(run())
        finally:
            fixture.close()


async def _expire_silent_pi(project, document, access, broker, clock, monkeypatch):
    checks = []

    def observe(check):
        def run(**active):
            now = clock[0]
            result = check(**active)
            checks.append(now)
            return result
        return run

    for method in ('refresh', 'require_active'):
        monkeypatch.setattr(broker, method, observe(getattr(broker, method)))

    path = PREFIX + f"/sessions/{document['scope']['session_id']}/attachments:"
    reviewed = await asyncio.to_thread(project.http, 'POST', path + 'review', document | {'access': access})
    fields = {'expected_writer_epoch': reviewed['writer_epoch']} if access == 'write' else {}
    offer = await asyncio.to_thread(project.http, 'POST', path + 'prepare', document | fields | {
        'client_intent_id': 'silent-pi', 'intent': 'attach_live', 'access': access,
        'capability_revision': reviewed['capability_revision']})
    path = PREFIX + f"/attachments/{offer['attachment_id']}/stream"
    headers = {'Authorization': 'Bearer ' + offer['ticket'], 'Cookie': project.http.request_headers()['Cookie']}

    async with connect(project.origin.replace('http://', 'ws://', 1) + path,
            subprotocols=[REMOTE_PI_SUBPROTOCOL], origin=project.origin, additional_headers=headers) as socket:
        async def exchange(frame):
            await socket.send(canonical_json(frame).decode())
            return json.loads(await asyncio.wait_for(socket.recv(), 8))

        challenge = await exchange({'kind': 'hello', 'version': 1, 'scope': document['scope'],
            'expected_session_generation': document['expected_session_generation'], 'columns': 100,
            'rows': 30, 'editor': access == 'write'})
        attached = await exchange({'kind': 'prove', 'challenge': challenge['challenge']})
        assert attached['access'] == access
        assert isinstance(await asyncio.wait_for(socket.recv(), 8), bytes)
        expiry = project.rows('session_attachments')[0]['expires_monotonic']
        clock[0] += 10
        await asyncio.wait_for(await socket.ping(), 5)
        await project.eventually(lambda: clock[0] in checks)
        assert project.rows('session_attachments')[0]['expires_monotonic'] == expiry
        assert offer['pi_keepalive'] is True
        clock[0] = expiry + 1
        with pytest.raises(ConnectionClosed):
            await asyncio.wait_for(socket.recv(), 5)
    await project.eventually(lambda: [r['state'] for r in project.rows('session_attachments')] == ['DETACHED'])
