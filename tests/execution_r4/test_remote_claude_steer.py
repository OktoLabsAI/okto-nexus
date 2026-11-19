"""Run the real Nexus and Connector control links against a synthetic Claude peer."""

import asyncio
from dataclasses import replace

import pytest
import test_pr34_remediation as tcp
from nexus_connector_core import RuntimeEvent
from nexus_connector_core.native.adapter_types import ErrorCode, NativeAdapterError
from nexus_connector_core.targeted_control_link import CLAUDE_OPERATION_STEER_CODEC
from remote_renewal_helpers import RemoteProject

from okto_nexus.adapters.inbound.cli.session_commands import (
    execute_session_command,
    recover_session_command,
)
from okto_nexus.application.terminal_connection import PREFIX, ConnectionError


def test_remote_claude_command_retains_exact_target_and_uncertain_replacement(tmp_path, monkeypatch, request):
    original = tcp.build_app

    def app(deps, **kwargs):
        deps.config.runtime_session_interaction_enabled = True
        return original(deps, **kwargs)

    monkeypatch.setattr(tcp, 'build_app', app)
    for module in ('availability', 'executor_inventory'):
        monkeypatch.setattr(f'nexus_connector_core.{module}.qualified_build', lambda *_args, **_kwargs: True)

    with pytest.MonkeyPatch.context() as fixture_patch:
        fixture = tcp._runtime(tmp_path, request, fixture_patch)
        runtime = next(fixture)
        project = RemoteProject(runtime, tmp_path, monkeypatch, actions=12, adapter_id='claude_stream')
        project.observed = replace(project.observed, architecture='x86_64')

        async def run():
            try:
                await project.start()
                negotiated = CLAUDE_OPERATION_STEER_CODEC.revision
                assert negotiated in project.control.connection.state.control_capabilities
                opened = await asyncio.to_thread(project.work().submit, 'Synthetic original Claude prompt', new_session=True,
                                                 client_intent_id='remote-claude-live')
                await project.operation(opened['operation_id'], stage='SUBMITTED')
                active_id = opened['submission_turn_operation_id']
                await project.operation(active_id, stage='SUBMITTED')
                scope = opened['scope']
                session = scope['session_id']
                generation = scope['session_owner_generation']
                binding = await asyncio.to_thread(project.work().binding)
                native, epoch, _ = project.native.opened[session]
                path = PREFIX + f'/runtime/sessions/{session}'

                def event(kind, native_type, payload, operation_id):
                    return RuntimeEvent(scope['server_id'], scope['executor_id'], session, epoch, 0,
                                        kind, native_type, payload, operation_id=operation_id)

                def read(prompt):
                    if prompt == 'Message: ':
                        return 'Synthetic replacement from the CLI'
                    assert prompt == 'Interrupt the current Claude turn and send this replacement message? [y/N] '
                    return 'yes'

                offered = []

                def review_command():
                    return execute_session_command(project.http, binding, session, 'steer', interactive=True,
                                                   message_file=None, read=read, write=offered.append)

                with pytest.raises(ConnectionError, match='no current review'):
                    await asyncio.to_thread(review_command)
                assert not offered

                await native.queue.put(event('tool_activity', 'nexus_claude_generating', {'schema_version': 1}, active_id))
                await project.eventually(lambda: any('nexus_claude_generating' in row['payload_json']
                    for row in project.rows('execution_event_ingress')))

                # A rolling upgrade can leave the current capacity host without
                # the extension. The generating fact alone confers no control.
                host = project.deps.runtime_availability.current_host(scope['server_id'], scope['executor_id'])
                current = host.channel
                host.channel = replace(current, control_capabilities=tuple(
                    revision for revision in current.control_capabilities if revision != negotiated))
                try:
                    with pytest.raises(ConnectionError, match='no current review'):
                        await asyncio.to_thread(review_command)
                finally:
                    host.channel = current
                assert not offered and not project.rows('session_interaction_inputs')

                effects = []
                send = native.send

                async def uncertain_replacement(verb, payload, operation_id, *, expected_turn_id=None):
                    if verb != 'steer':
                        return await send(verb, payload, operation_id, expected_turn_id=expected_turn_id)
                    effects.append((operation_id, payload['expected_claude_operation_id'], payload['text']))
                    for stage in ('interrupt_submitted', 'interrupt_confirmed', 'replacement_write_unknown'):
                        await native.queue.put(event('tool_activity', 'nexus_claude_steer', {
                            'stage': stage, 'interrupt_request_id': 'fixture-interrupt', 'turn_operation_id': active_id,
                        }, operation_id))
                    await native.queue.put(event('turn_state', 'fixture.claude.interrupt', {
                        'delivery_phase': 'terminal', 'delivery_outcome': 'interrupted',
                    }, active_id))
                    raise NativeAdapterError(ErrorCode.INTERNAL_ERROR, 'Synthetic uncertainty after the replacement write')

                native.send = uncertain_replacement
                project.lose_next = path + '/terminal/commands:execute'

                class LostReply:
                    token = project.http.token
                    __call__ = staticmethod(project.call)

                result = await asyncio.to_thread(execute_session_command, LostReply(), binding, session, 'steer',
                    interactive=True, message_file=None, read=read, write=offered.append)
                assert result['state'] == 'recorded' and project.lose_next is None
                intent = result['client_intent_id']
                await project.eventually(lambda: any(row['status'] == 'DELIVERY_UNKNOWN'
                    for row in project.rows('session_interaction_inputs')))
                await project.eventually(lambda: any('replacement_write_unknown' in row['payload_json']
                    for row in project.rows('execution_event_ingress')))
                receipt = await asyncio.to_thread(recover_session_command, project.http, binding, session, generation, intent)
                assert receipt['receipt']['steer_compound'] == {
                    'interruption': 'confirmed', 'replacement': 'write_unknown',
                }
                assert receipt['message'] == 'Claude interruption confirmed. Replacement message delivery is unconfirmed.'
                operation_id = receipt['receipt']['operation_id']
                assert effects == [(operation_id, active_id, 'Synthetic replacement from the CLI')]
                retained, = project.rows('session_interaction_claude_steer_targets')
                assert (retained['operation_id'], retained['target_operation_id'], retained['target_stream_epoch']) == (
                    operation_id, active_id, epoch)
                assert len([row for row in project.rows('execution_operations') if row['action'] == 'turn.steer']) == 1
                with pytest.raises(ConnectionError, match='no current review'):
                    await asyncio.to_thread(review_command)

                await native.queue.put(event('turn_state', 'fixture.claude.late_result', {
                    'delivery_phase': 'terminal', 'delivery_outcome': 'success',
                }, operation_id))
                await project.eventually(lambda: any(row['status'] == 'ACCEPTED_NATIVE'
                    for row in project.rows('session_interaction_inputs')))
                assert len(effects) == 1 and project.control.connection.online
                closed = await asyncio.to_thread(project.work().submit, action='close', session_id=session,
                                                 client_intent_id='remote-claude-close')
                await project.operation(closed['operation_id'])
            finally:
                await project.close()

        try:
            asyncio.run(run())
        finally:
            fixture.close()
