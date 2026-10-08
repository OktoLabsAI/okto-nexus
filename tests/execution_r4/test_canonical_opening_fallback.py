"""An actual native startup failure can use an approved unsent alternative."""
import sys
import json
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract
from test_canonical_delivery import connected_local, enable, send
from test_canonical_identity_lifecycle import second_binding
from test_canonical_delivery_retry import wait_delivery
from test_harness_codex_connector import _FAKE_SERVER_SOURCE


def test_incompatible_native_opening_preserves_unsent_child_and_approved_fallback(connected_local, monkeypatch):
    from nexus_connector_core.native import runtime_bridge
    from nexus_connector_core.native.adapters.codex import CodexAppServerConnector
    from test_vertical_inventory import _Native
    setup, first, _ = connected_local
    clock = [setup[0].clock.now_iso()]
    monkeypatch.setattr(setup[0].clock, 'now_iso', lambda: clock[0])
    second = second_binding(setup, monkeypatch)
    for binding in (first, second):
        enable(setup, binding)
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET selection_group='startup-alternatives',priority=1")
        uow.connection.execute('UPDATE agent_endpoints SET priority=10 WHERE endpoint_id=?', (first['endpoint_id'],))
    root = setup[-1]
    wire = root / 'opening-wire.jsonl'
    source = _FAKE_SERVER_SOURCE.replace('thread_id = next_thread_id()', 'thread_id = None')
    source = source.replace('method = msg.get("method")', 'method = msg.get("method"); log({"method": method})')
    peers = []
    def construct(**options):
        peer = CodexAppServerConnector(command=[sys._base_executable, '-u', '-c', source, str(wire)], cwd=str(root), env={})
        peers.append(peer)
        return peer
    monkeypatch.setattr(runtime_bridge, 'qualified_build', lambda *a, **k: True)
    monkeypatch.setattr(runtime_bridge, 'load_adapter', lambda _: construct)
    async def environment(prepared):
        return {}
    bridge = runtime_bridge.CopiedAdapterFactory(environment)
    healthy = _Native()
    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch):
            if prepared.intent.adapter_id == 'codex_app_server':
                return await bridge.open(prepared, session_id, context, stream_epoch=stream_epoch)
            return healthy
    setup[1].state.embedded_dispatch_owner.native_factory = Factory()
    try:
        assert send(setup, monkeypatch)['ok']
        row = wait_delivery(setup, lambda row: row['status'] == 'RETRY_WAIT' and row['reason'] == 'native_write_not_started')
        assert row['retry_basis'] == 'HOST_NO_SEND'
        assert len(peers) == 1
        assert peers[0]._transport is None or peers[0]._transport._proc.poll() is not None
        assert not any(json.loads(line).get('method') == 'turn/start'
            for line in wire.read_text(encoding='utf-8').splitlines())
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            opening = dict(uow.connection.execute("SELECT operation_id,session_id FROM execution_operations WHERE action='runtime.open'").fetchone())
            receipt = uow.connection.execute('SELECT stage,possible_effect,retry_safe FROM execution_receipts WHERE operation_id=?', (opening['operation_id'],)).fetchone()
            assert tuple(receipt) == ('FAILED', 1, 0)
            assert uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions WHERE session_id=?',
                (opening['session_id'],)).fetchone()[:] == ('CLOSED', 'CLOSED')
            original_turn = uow.connection.execute("SELECT operation_id FROM execution_operations WHERE action='turn.submit'").fetchone()[0]
            assert uow.connection.execute('SELECT count(*) FROM execution_receipts WHERE operation_id=?', (original_turn,)).fetchone()[0] == 0
            assert uow.connection.execute('SELECT count(*) FROM execution_unsent_delivery_history').fetchone()[0] == 2
        assert json.loads(row['next_binding'])['endpoint_id'] == second['endpoint_id']
        original = row
        clock[0] = row['next_attempt_at']
        setup[0].runtime_dispatcher.wake()
        row = wait_delivery(setup, lambda row: row['status'] == 'ACCEPTED')
        assert row['endpoint_id'] == second['endpoint_id']
        assert row['attempt_id'] != original_turn
        assert all(row[k] == original[k] for k in ('operation_id', 'message_id', 'delivery_id', 'envelope', 'request_hash'))
        assert len(healthy.sent) == 1
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT stage,possible_effect,retry_safe FROM execution_receipts WHERE operation_id=?',
                (opening['operation_id'],)).fetchone()[:] == ('FAILED', 1, 0)
            assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()
    finally:
        bridge.close()
