"""Revoked admission never discards already captured native evidence."""
import json
import threading

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_native_protocol_regressions import install_native
from test_canonical_result_publication import current_turn, emit, wait_result
from test_canonical_handoff import prepare
from test_canonical_grant_regressions import mcp_helpers, invoke_command
from test_harness_codex_connector import _FAKE_SERVER_SOURCE


def test_grant_revoked_during_native_work_retains_terminal_without_completion(connected_local, monkeypatch):
    setup, binding, _ = connected_local
    release = setup[-1] / 'release-revoked-work'
    gate = ('    deadline = time.monotonic() + 30\n'
        f'    while not os.path.exists({str(release)!r}):\n'
        '        assert time.monotonic() < deadline\n'
        '        time.sleep(.01)\n')
    result = ('    envelope = json.loads(text.split("\\n", 1)[1])\n'
        '    text = json.dumps({"nexus_work_result": {"schema_version": 1, '
        '"operation_id": envelope["operation_id"], "handoff_id": envelope["handoff_id"], '
        '"claim_epoch": envelope["claim_epoch"], "action": "complete", "result": "Retained revoked evidence"}})\n')
    marker = '    item_id = "item_" + turn_id'
    assert marker in _FAKE_SERVER_SOURCE
    peers, log = install_native(connected_local, _FAKE_SERVER_SOURCE.replace(marker, gate + result + marker))
    hid, grant, claim, _ = prepare(setup, binding, monkeypatch)
    try:
        admitted = claim(completion_mode='structured_result_v1')
        assert admitted['ok'], admitted
        turn = current_turn(setup)
        wait_receipt(setup, turn)
        # The fixture has an independent conversation grant as well as the
        # work grant. Revoke both before asserting there is no send authority.
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            grants = [r[0] for r in uow.connection.execute(
                "SELECT grant_id FROM runtime_execution_grants WHERE actor_agent_id='subject' AND revoked_at IS NULL")]
        assert grant in grants
        for grant_id in grants:
            revoked = setup[2].delete('/api/v1/harness/grants/' + grant_id, headers=setup[3]['operator'])
            assert revoked.status_code == 200, revoked.text
        for surface in ('rest', 'mcp'):
            denied = invoke_command(setup, monkeypatch, surface, turn['session_id'],
                dict(idempotency_key='revoked-' + surface, payload=dict(text='Must not execute')))
            assert not denied['ok'] and denied['error']['code'] == 'PERMISSION_DENIED', denied
    finally:
        release.touch()
    retained = wait_result(setup, 'BLOCKED')
    assert 'Retained revoked evidence' in retained['output_text']
    assert not retained['publication_message_id']
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,result FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[:] == ('CLAIMED', None)
        assert uow.connection.execute('SELECT count(*) FROM delivery_outbox').fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 1
    assert len(peers) == 1
    assert sum(row.get('method') == 'turn/start' for row in map(json.loads, log.read_text(encoding='utf-8').splitlines())) == 1


def test_feature_disable_preserves_unprojected_terminal_and_exclusive_claim(connected_local, monkeypatch):
    from okto_nexus.bootstrap import embedded_events
    from test_canonical_consumption import pull
    setup, binding, native = connected_local
    enable(setup, binding)
    sent = send(setup, monkeypatch)
    assert sent['ok'], sent
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    captured = threading.Event()
    release = threading.Event()
    original = embedded_events.commit_execution_events
    def deferred(*args, **kwargs):
        if not release.is_set():
            captured.set()
            raise OSError('Server projection unavailable after Core durable capture')
        return original(*args, **kwargs)
    monkeypatch.setattr(embedded_events, 'commit_execution_events', deferred)
    try:
        emit(setup, native, turn, 'Captured before disabling admission', wait_for_terminal=False)
        assert captured.wait(10)
        changed = setup[2].patch('/api/v1/settings', headers=setup[3]['operator'],
                                json={'feature_harness_integrations': False})
        assert changed.status_code == 200, changed.text
        denied = invoke_command(setup, monkeypatch, 'rest', turn['session_id'],
            dict(idempotency_key='disabled-turn', payload=dict(text='Must not execute')))
        assert not denied['ok'], denied
        assert pull(setup, monkeypatch) == []
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            assert not uow.connection.execute('SELECT 1 FROM runtime_results').fetchone()
    finally:
        release.set()
    retained = wait_result(setup, 'PENDING_AUTHORIZATION')
    setup[0].runtime_dispatcher.publish_results()
    assert retained['output_text'] == 'Captured before disabling admission'
    assert not retained['publication_message_id']
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM delivery_outbox').fetchone()[0] == 1
        assert uow.connection.execute('SELECT max(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1
    assert native.opens == 1 and len(native.native.sent) == 1
