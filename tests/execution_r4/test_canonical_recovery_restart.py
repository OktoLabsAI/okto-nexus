"""Recovery survives restart and never restores the retired stdio owner."""
from contextlib import contextmanager
import os
import subprocess
import sys

from fastapi.testclient import TestClient
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, connect_local
from test_canonical_delivery import connected_local
from test_canonical_grant_regressions import mcp_helpers
from test_canonical_recovery_regressions import uncertain, post, body
from test_embedded_inventory import app_for
from test_pr34_remediation import tool


def test_retired_stdio_refuses_conversation_recovery_without_replaying(connected_local, monkeypatch):
    setup, _, row, native = uncertain(connected_local, monkeypatch)
    deps = setup[0]
    owner = (deps.runtime_dispatcher.owner_id, deps.runtime_dispatcher.epoch)
    token = setup[3]['operator']['Authorization'].removeprefix('Bearer ')
    retired = subprocess.run([sys.executable, '-m', 'okto_nexus.adapters.inbound.mcp.server',
        '--home', str(deps.config.home_dir)], env=dict(os.environ, OKTO_NEXUS_API_KEY=token),
        capture_output=True, text=True, timeout=30)
    assert retired.returncode != 0 and 'MCP stdio is no longer available' in retired.stderr
    response = post(setup, body(row))
    assert response.status_code == 200, response.text
    setup[2].headers['host'] = '127.0.0.1:8000'
    repeat = tool(setup[2], token, 'harness_list', dict(view='outbox', maintenance=body(row)))
    assert repeat['ok'] and repeat['data'] == response.json()['data'], repeat
    assert (deps.runtime_dispatcher.owner_id, deps.runtime_dispatcher.epoch) == owner
    assert native.opens == 1 and len(native.native.sent) == 1


def test_restart_with_admission_disabled_recovers_retained_conversation(tmp_path, monkeypatch):
    with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as initial:
        setup, _, row, native = uncertain(connected_local.__wrapped__(initial), monkeypatch)
        retained = setup
        home = setup[0].config.home_dir
    assert native.opens == 1 and len(native.native.sent) == 1
    deps, app = app_for(home)
    deps.config.feature_harness_integrations = False
    with TestClient(app) as client:
        assert not hasattr(app.state, 'embedded_dispatch_owner')
        setup = (deps, app, client, *retained[3:])
        inspected = client.get('/api/v1/harness/outbox', headers=setup[3]['operator'], params=dict(operation_id=row['operation_id']))
        assert inspected.status_code == 200, inspected.text
        response = post(setup, body(row))
        assert response.status_code == 200, response.text
        assert response.json()['data']['native_replayed'] is False
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM execution_sessions WHERE lifecycle_state!='CLOSED'").fetchone()[0] == 0
    assert native.opens == 1 and len(native.native.sent) == 1
