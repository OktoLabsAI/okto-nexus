"""Real owner crashes recover durable launches without operator repair/replay."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from nexus_connector_core import InstallationCandidate, OperationKey, SessionKey
from nexus_connector_core.discovery import fingerprint
from okto_nexus.adapters.inbound.http.lock import ServeLock
from okto_nexus.bootstrap import embedded_inventory

from test_agent_recovery_isolation import eventually
from test_embedded_dispatch import admit, wait_receipt
from test_embedded_inventory import app_for
from test_vertical_inventory import _NativeFactory


@pytest.mark.skipif(sys.platform != 'win32', reason='Actual Windows Job owner-crash recovery')
@pytest.mark.parametrize('boundary', ['intent', 'effect', 'claim', 'container', 'spawn', 'birth'])
def test_embedded_restart_recovers_interrupted_launch_automatically(tmp_path, monkeypatch, boundary):
    root = tmp_path/'disposable'
    root.mkdir()
    fixture = Path(__file__).with_name('launch_recovery_process_fixture.py')
    paths = json.dumps([str(Path(p).resolve()) for p in sys.path if p])
    code = 'import sys,json,runpy; sys.path[:]=json.loads(sys.argv.pop(1)); runpy.run_path(sys.argv.pop(1),run_name="__main__")'
    result = subprocess.run([sys.executable, '-I', '-c', code, paths, str(fixture), str(root), boundary],
        capture_output=True, text=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 17, result.stderr[-5000:]
    state = json.loads((root/'opening.json').read_text(encoding='utf-8'))
    binary = root/'codex.exe'
    candidate = InstallationCandidate('codex_app_server', str(binary), fingerprint(binary), 'explicit', 'selected')
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates',
        lambda **_: SimpleNamespace(candidates=tuple(c for c in (candidate,) if not _.get('adapter_ids') or c.adapter_id in _['adapter_ids'])))
    with ServeLock(root/'home'):
        deps, app = app_for(root/'home')
        with TestClient(app) as client:
            owner = app.state.embedded_dispatch_owner
            eventually(lambda: not owner.agents.blocked, seconds=25)
            assert owner.failure is None and owner.pump is not None
            with deps.connection_factory.unit_of_work(write=False) as uow:
                session = dict(uow.connection.execute('SELECT * FROM execution_sessions WHERE session_id=?',
                    (state['session_id'],)).fetchone())
                assert session['lifecycle_state'] == ('FAILED' if boundary in ('intent', 'effect') else 'CLOSED')
                assert session['lease_state'] == 'CLOSED'
                assert uow.connection.execute('SELECT count(*) FROM execution_operations').fetchone()[0] == 1
                assert uow.connection.execute('SELECT max(attempt_no) FROM execution_dispatch_outbox').fetchone()[0] == 1
                assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()
            async def verify_history():
                key = SessionKey(owner.channel.server_id, owner.channel.executor_id, state['session_id'])
                async def inspect(journal):
                    launch = await journal.get_process_launch(key)
                    receipt = await journal.get_receipt(OperationKey(key.server_id, key.executor_id, state['operation_id']))
                    assert launch.stop_proof == ('NEVER_CLAIMED' if boundary in ('intent', 'effect') else 'CONTAINER_STOPPED')
                    assert receipt.possible_effect is (boundary != 'intent')
                    assert receipt.stage == ('FAILED' if boundary in ('intent', 'effect') else 'SUBMISSION_STARTED')
                await owner.host.with_history(executor_id=key.executor_id, session_id=key.session_id, read=inspect)
                assert not (await (await owner.host._ledger()).owned_slot_page()).reservations
            client.portal.call(verify_history)
            # A new request on the original agent works without a retry/repair API.
            native = _NativeFactory()
            owner.native_factory = native
            setup = deps, app, client, state['headers'], state['body'], candidate, root/'workspace'
            key = (state['binding']['server_id'], state['binding']['executor_id'])
            def binding_ready():
                from okto_nexus.application.execution_inventory_freshness import inventory_is_fresh
                from okto_nexus.application.execution_inventory_revalidation import accepts_binding
                marker = app.state.inventory_fresh_publications.get(key)
                with deps.connection_factory.unit_of_work(write=False) as uow:
                    conn = uow.connection
                    published = conn.execute(
                        'SELECT c.publication_sequence,c.inventory_revision,s.observation_age_ms,'
                        's.canonical_projection FROM execution_inventory_current c '
                        'JOIN execution_inventory_snapshots s ON s.server_id=c.server_id '
                        'AND s.executor_id=c.executor_id AND s.publication_sequence=c.publication_sequence '
                        'WHERE c.server_id=? AND c.executor_id=?', key).fetchone()
                    if marker is None or published is None or marker[0] != published['publication_sequence']:
                        return False
                    binding = conn.execute(
                        'SELECT b.inventory_revision,b.candidate_ref,ep.adapter_id,e.control_state '
                        'FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id '
                        'JOIN execution_executors e ON e.server_id=b.server_id AND e.executor_id=b.executor_id '
                        'WHERE b.server_id=? AND b.binding_id=?',
                        (key[0], state['binding']['binding_id'])).fetchone()
                    return (binding is not None and binding['control_state'] == 'CONTROL_READY'
                        and inventory_is_fresh(published, marker, binding['adapter_id'])
                        and accepts_binding(conn, binding, published['inventory_revision'], *key))
            eventually(binding_ready, seconds=25)
            replacement = admit(setup, state['binding'], 'new-after-crash', 'runtime.start', new_session=True)
            wait_receipt(setup, replacement)
            assert replacement['session_id'] != state['session_id']
