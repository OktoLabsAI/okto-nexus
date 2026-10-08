"""The current Core scrubs native text before durable Server projections."""
import json

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_native_protocol_regressions import open_native, events
from test_canonical_claude_approvals import completed_result
from test_harness_codex_connector import _FAKE_SERVER_SOURCE

SECRET = 'fixture-opaque-backend-credential-43816'


@pytest.mark.parametrize('fragmentation', ['single', 'split', 'characters'])
def test_native_secret_is_redacted_before_durable_result_and_replay(connected_local, caplog, fragmentation):
    original = next(line for line in _FAKE_SERVER_SOURCE.splitlines() if '"delta": text' in line)
    fragments = {'single': '["safe before " + value + " safe after"]',
        'split': '["safe before " + value[:17], value[17:] + " safe after"]',
        'characters': '["safe before "] + list(value) + [" safe after"]'}[fragmentation]
    source = _FAKE_SERVER_SOURCE.replace(original,
        '    value = os.environ["FIXTURE_BACKEND_KEY"]\n'
        '    for fragment in ' + fragments + ':\n' +
        original.replace('"delta": text', '"delta": fragment').replace('    write_msg', '        write_msg'))
    assert source != _FAKE_SERVER_SOURCE
    setup, binding, sid, peer, _ = open_native(connected_local, source, environment={'FIXTURE_BACKEND_KEY': SECRET})
    for index in range(2):
        turn = admit(setup, binding, 'secret-turn-' + str(index), 'turn.submit', session_id=sid, text='Fixture diagnostic')
        result = completed_result(setup, turn)
        assert result['output_text'] == 'safe before [REDACTED] safe after'
    captured = events(setup)
    assert SECRET not in json.dumps(captured)
    assert SECRET not in ''.join(str(e['payload'].get('delta', '')) for e in captured)
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert SECRET not in json.dumps([dict(r) for r in uow.connection.execute('SELECT * FROM execution_results')])
    assert SECRET not in caplog.text
    wait_receipt(setup, admit(setup, binding, 'secret-close', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))
    assert peer._transport._proc.wait(timeout=5) is not None


@pytest.mark.parametrize('adapter', ['codex_app_server', 'claude_stream'])
@pytest.mark.parametrize('decision', ['approve', 'deny'])
def test_native_secret_in_approval_is_private_and_exact_reply_remains_valid(connected_local, adapter, decision):
    if adapter == 'codex_app_server':
        from test_canonical_native_approvals import approval_peer
        setup, binding, turn, body, peer, log = approval_peer(connected_local,
            extra_params={'command': 'fixture ' + SECRET}, redaction_values=(SECRET,))
    else:
        from test_canonical_claude_approvals import native_peer
        setup, binding, turn, body, log, peer = native_peer(connected_local,
            inputs={'file_path': 'fixture.txt', 'content': SECRET}, redaction_values=(SECRET,))
    # The display is redacted; the protected native request retains correlation.
    listing = setup[2].get('/api/v1/approvals', headers=setup[3]['operator'],
        params={'workspace': binding['workspace_id'], 'status': 'pending'})
    assert listing.status_code == 200 and SECRET not in listing.text
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        rows = [dict(r) for r in uow.connection.execute('SELECT * FROM execution_native_requests')]
        assert len(rows) == 1 and SECRET not in rows[0]['display_json']
        # R4 stores the original operational request separately to validate
        # exact native replies. Only its scrubbed presentation is public.
        assert SECRET in rows[0]['operational_frame_json']
    for approval in listing.json()['data']['items']:
        detail = setup[2].get('/api/v1/approvals/' + approval['approval_id'], headers=setup[3]['operator'])
        assert detail.status_code == 200 and SECRET not in detail.text
    assert setup[2].post('/v1/runtime/approval-decisions', headers=setup[3]['subject'], json=body).status_code == 403
    response = setup[2].post('/v1/runtime/approval-decisions', headers=setup[3]['operator'], json=dict(body, decision=decision))
    assert response.status_code == 202, response.text
    result = completed_result(setup, turn)
    assert SECRET not in result['output_text']
    for role in ('subject', 'operator'):
        for path in (f"/v1/runtime/sessions/{turn['session_id']}/events",
                     f"/api/v1/harness/sessions/{turn['session_id']}/events"):
            replay = setup[2].get(path, headers=setup[3][role])
            assert replay.status_code == 200, replay.text
            assert SECRET not in replay.text
    from test_pr34_remediation import tool
    setup[2].headers['host'] = '127.0.0.1:8000'
    replay = tool(setup[2], setup[3]['subject']['Authorization'].removeprefix('Bearer '),
                  'harness_event_list', dict(session_id=turn['session_id']))
    assert replay['ok'] and SECRET not in json.dumps(replay)
    wire = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    if adapter == 'codex_app_server':
        replies = [r['response_to_server_request'] for r in wire if 'response_to_server_request' in r]
        assert len(replies) == 1 and replies[0]['id'] == 9001
        assert replies[0]['result']['decision'] == ('accept' if decision == 'approve' else 'decline')
    else:
        replies = [r for r in wire if r.get('type') == 'control_response']
        assert len(replies) == 1 and replies[0]['response']['request_id'] == 'permission-1'
        assert replies[0]['response']['response']['behavior'] == ('allow' if decision == 'approve' else 'deny')
    wait_receipt(setup, admit(setup, binding, 'private-approval-close', 'runtime.close', session_id=turn['session_id']), stages=('SUCCEEDED',))
    proc = peer._transport._proc if adapter == 'codex_app_server' else peer._proc
    assert proc.wait(timeout=5) is not None
