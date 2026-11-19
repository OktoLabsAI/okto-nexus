"""Real HTTP/Connector WebSocket and canonical lease with a synthetic Codex read."""

import asyncio
from dataclasses import asdict

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
from remote_renewal_helpers import RemoteProject

from okto_nexus.adapters.inbound.http.operator_auth import COOKIE
from okto_nexus.adapters.outbound.execution.presentation_link import PresentationLink
from okto_nexus.application.execution_leases import ExecutionChannel
from okto_nexus.domain.execution.keys import SessionKey, SessionOwnerGeneration
from okto_nexus.domain.session_interaction import InputAuthor, InputScope

_THREAD = 'bdfe5b81-54cf-43cf-8001-5de670d3dd69'
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


def test_human_reads_exact_remote_codex_context_and_logout_discards_inflight_result(tmp_path, monkeypatch, request):
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
        if len(reads) == 2:
            entered.set()
            await release.wait()
        return {'viewer_context': {'thread_id': thread_id, 'session_id': 'native-viewer-synthetic', 'cwd': cwd,
            'model': 'synthetic', 'model_provider': 'fixture', 'status': 'active', 'created_at': 1,
            'updated_at': 2, 'ephemeral': False, 'cli_version': '0.157.0', 'source': 'cli',
            'approval_policy': 'on-request', 'approvals_reviewer': 'user', 'sandbox': {'type': 'readOnly'},
            'reasoning_effort': 'medium'}}

    monkeypatch.setattr(LocalRuntimeCore, 'read_live_codex_thread', peer)
    with pytest.MonkeyPatch.context() as fixture_patch:
        fixture = tcp._runtime(tmp_path, request, fixture_patch)
        runtime = next(fixture)
        project = RemoteProject(runtime, tmp_path, monkeypatch)

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
