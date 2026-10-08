"""A Claude replacement retains separate results through public control APIs."""
import asyncio
import sys

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_grant_regressions import mcp_helpers
from test_canonical_native_protocol_regressions import events
from test_agent_recovery_isolation import eventually


@pytest.mark.parametrize('local_setup', ['claude_stream'], indirect=True)
@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_claude_replacement_has_separate_public_results(connected_local, surface):
    from nexus_connector_core.native.adapters.claude_code_stream import ClaudeCodeStreamConnector
    from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
    from test_harness_claude_code_connector import _FAKE_CLAUDE_SCRIPT
    from test_pr34_remediation import tool

    setup, binding, _ = connected_local
    client, headers = setup[2:4]
    client.headers['host'] = '127.0.0.1:8000'
    peers = []

    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            peer = ClaudeCodeStreamConnector(binary=sys._base_executable,
                argv=['-u', '-c', _FAKE_CLAUDE_SCRIPT],
                version_argv=['-c', "print('2.1.281 (Claude Code)')"],
                cwd=str(setup[-1]), env={'FAKE_CC_SCENARIO': 'slow_start'})
            peers.append(peer)
            native = await asyncio.to_thread(peer.start, owning_agent_id=context.agent_id)
            return CopiedAdapterSession(peer, native, session_id=session_id,
                stream_epoch=stream_epoch, context=context)

    setup[1].state.embedded_dispatch_owner.native_factory = Factory()
    opened = admit(setup, binding, 'replacement-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    session = opened['scope']['session_id']

    def command(verb, text):
        body = dict(idempotency_key='replacement-' + verb, payload=dict(text=text))
        if surface == 'rest':
            response = client.post(f'/api/v1/harness/sessions/{session}/{verb}',
                headers=headers['subject'], json=body)
            assert response.status_code == 200, response.text
            result = response.json()
        else:
            result = tool(client, headers['subject']['Authorization'].removeprefix('Bearer '),
                'harness_' + verb, dict(session_id=session, **body))
        assert result['ok'], result
        return result['data']

    original = command('send', 'original')
    eventually(lambda: any(e.get('session_id') == session
        and e.get('native_type') == 'stream_event:content_block_start' for e in events(setup)))
    replacement = command('steer', 'replacement')
    assert original['operation_id'] != replacement['operation_id']
    wait_receipt(setup, original, stages=('CANCELLED',))
    wait_receipt(setup, replacement, stages=('SUCCEEDED',))

    def result(operation):
        response = client.get('/api/v1/harness/operations/' + operation['operation_id'],
            headers=headers['subject'])
        assert response.status_code == 200, response.text
        return response.json()['data'].get('result')

    eventually(lambda: result(original) and result(replacement))
    first, second = result(original), result(replacement)
    assert first['delivery_outcome'] == 'interrupted'
    assert second['delivery_outcome'] == 'success'
    assert 'echo:replacement' in second['output_text']
    assert 'echo:replacement' not in first['output_text']
    assert command('steer', 'replacement')['operation_id'] == replacement['operation_id']
    assert result(replacement) == second
    assert len(peers) == 1
    wait_receipt(setup, admit(setup, binding, 'replacement-close', 'runtime.close',
        session_id=session), stages=('SUCCEEDED',))
