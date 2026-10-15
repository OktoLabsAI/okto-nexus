"""Closing uncertain work preserves its identity while a fresh session can run."""
import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_grant_regressions import mcp_helpers, open_scoped, invoke_command


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_uncertain_command_replays_history_and_allows_fresh_session(connected_local, monkeypatch, surface):
    setup, binding, native, _, sid = open_scoped(connected_local)
    body = dict(idempotency_key='uncertain-command', payload=dict(text='Original uncertain work'))
    sent = invoke_command(setup, monkeypatch, surface, sid, body)
    assert sent['ok'], sent
    wait_receipt(setup, sent['data'])
    first_peer = native.native
    closed = admit(setup, binding, 'close-uncertain-command', 'runtime.close', session_id=sid)
    wait_receipt(setup, closed, stages=('SUCCEEDED',))
    before = wait_receipt(setup, sent['data'], stages=('SUBMITTED', 'OUTCOME_UNKNOWN'))
    assert before['possible_effect'] and not before['retry_safe']
    repeated = invoke_command(setup, monkeypatch, surface, sid, body)
    assert repeated['ok'], repeated
    assert repeated['data']['operation_id'] == sent['data']['operation_id']
    assert wait_receipt(setup, repeated['data'], stages=('SUBMITTED', 'OUTCOME_UNKNOWN')) == before
    assert len(first_peer.sent) == 1 and first_peer.stopped
    opened = admit(setup, binding, 'fresh-after-uncertain-command', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    fresh = invoke_command(setup, monkeypatch, surface, opened['scope']['session_id'],
        dict(idempotency_key='fresh-command', payload=dict(text='Independent new work')))
    assert fresh['ok'], fresh
    wait_receipt(setup, fresh['data'])
    assert native.opens == 2 and len(native.native.sent) == len(first_peer.sent) == 1
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 2
        assert uow.connection.execute('SELECT count(*) FROM messages').fetchone()[0] == 0
