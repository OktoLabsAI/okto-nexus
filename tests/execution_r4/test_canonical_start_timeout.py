"""A native handshake timeout cannot leave a ready session or replay its spawn."""
import json
import sys

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt


def test_rest_start_timeout_is_durable_contained_and_idempotent(connected_local, monkeypatch):
    from nexus_connector_core.native import runtime_bridge
    from nexus_connector_core.native.adapters.codex import CodexAppServerConnector
    setup, binding, _ = connected_local
    deps, app, client, headers, *_, root = setup
    marker = root / 'started-native.pid'
    source = f'import os,time; open({str(marker)!r}, "w").write(str(os.getpid())); time.sleep(60)'
    peers = []
    def construct(**options):
        peer = CodexAppServerConnector(command=[sys._base_executable, '-u', '-c', source],
            cwd=str(root), env={}, handshake_timeout_s=1)
        peers.append(peer)
        return peer
    monkeypatch.setattr(runtime_bridge, 'qualified_build', lambda *a, **k: True)
    monkeypatch.setattr(runtime_bridge, 'load_adapter', lambda _: construct)
    async def environment(prepared):
        return {}
    bridge = runtime_bridge.CopiedAdapterFactory(environment)
    app.state.embedded_dispatch_owner.native_factory = bridge
    with deps.connection_factory.unit_of_work(write=False) as uow:
        before = dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='subject'").fetchone())
        count = uow.connection.execute('SELECT count(*) FROM agents').fetchone()[0]
    body = dict(agent_id='subject', kind='codex', endpoint_id=binding['endpoint_id'],
                project_root=str(root), idempotency_key='start-timeout')
    try:
        response = client.post('/api/v1/harness/sessions', headers=headers['subject'], json=body)
        assert response.status_code == 200, response.text
        opened = response.json()['data']
        failed = wait_receipt(setup, opened, stages=('FAILED',))
        assert marker.exists() and len(peers) == 1
        assert failed['possible_effect'] is True and 'NATIVE_STARTUP_FAILED' in json.dumps(failed)
        transport = peers[0]._transport
        assert transport is None or transport._proc.poll() is not None
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert not uow.connection.execute("SELECT 1 FROM execution_sessions WHERE lifecycle_state='READY'").fetchone()
            after = dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='subject'").fetchone())
            # Authenticated requests legitimately update presence, not identity.
            assert {k: v for k, v in after.items() if k != 'last_seen_at'} == {k: v for k, v in before.items() if k != 'last_seen_at'}
            assert uow.connection.execute('SELECT count(*) FROM agents').fetchone()[0] == count
        replay = client.post('/api/v1/harness/sessions', headers=headers['subject'], json=body)
        assert replay.status_code == 200, replay.text
        assert replay.json()['data']['operation_id'] == opened['operation_id']
        assert wait_receipt(setup, replay.json()['data'], stages=('FAILED',))['possible_effect'] is True
        assert len(peers) == 1
    finally:
        bridge.close()
