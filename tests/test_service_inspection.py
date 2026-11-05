from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
import json
import os
import threading

import pytest

from okto_nexus.adapters.inbound.cli.service import run_service
from okto_nexus.adapters.inbound.http.lock import ServeLock
from okto_nexus.adapters.outbound.service_manager.identity import server_instance_id
from okto_nexus.adapters.outbound.service_manager.inspection import inspect_local_server


def test_status_of_absent_instance_does_not_create_home_or_start_process(tmp_path, monkeypatch, capsys):
    import subprocess
    home = tmp_path / 'absent'
    monkeypatch.setattr(subprocess, 'Popen', lambda *_a, **_kw: pytest.fail('Status started a process'))
    assert run_service(['status', '--home', str(home), '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'stopped'
    assert result['work_state'] == 'not_checked'
    assert not home.exists()


def test_remote_target_is_not_silently_treated_as_local(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('OKTO_NEXUS_HOME', str(tmp_path / 'absent'))
    assert run_service(['status', '--server', 'https://remote.example', '--json']) == 2
    assert json.loads(capsys.readouterr().out)['reason'] == 'CONFIG_ERROR'
    assert not (tmp_path / 'absent').exists()


@pytest.fixture
def endpoint(tmp_path):
    state = {'data': {}, 'redirect': False, 'requests': []}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state['requests'].append(self.path)
            if state['redirect']:
                self.send_response(302)
                self.send_header('Location', '/trap')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'ok': True, 'data': state['data']}).encode())
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    with ServeLock(tmp_path) as lock:
        state['data'] = {'component': 'server', 'instance_id': server_instance_id(lock.home_dir, lock.db_path),
            'generation': lock.generation, 'active_version': version('okto-nexus'),
            'pid': os.getpid(), 'state': 'ready', 'ready_for_queries': True,
            'storage_initialized': True, 'admission': 'canonical_scope_checks_required',
            'protocol_revision': 1}
        try:
            yield state, dict(home=tmp_path, database=lock.db_path,
                              host='127.0.0.1', port=server.server_port)
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()


def test_matching_identity_generation_version_and_os_owner_are_required(endpoint):
    state, args = endpoint
    assert inspect_local_server(**args)['state'] == 'ready'
    state['data']['generation'] = 'unrelated-process'
    assert inspect_local_server(**args)['reason'] == 'INSTANCE_MISMATCH'


def test_another_instance_on_the_port_is_not_ready(endpoint):
    state, args = endpoint
    state['data']['instance_id'] = 'svc_other'
    assert inspect_local_server(**args)['reason'] == 'INSTANCE_MISMATCH'


def test_active_version_drift_requires_explicit_review(endpoint):
    state, args = endpoint
    state['data']['active_version'] = '0.0.1'
    result = inspect_local_server(**args)
    assert result['state'] == 'degraded'
    assert result['reason'] == 'VERSION_INCOMPATIBLE'
    assert result['active_version'] == '0.0.1'


def test_redirect_is_not_followed(endpoint):
    state, args = endpoint
    state['redirect'] = True
    assert inspect_local_server(**args)['reason'] == 'SERVICE_UNREACHABLE'
    assert state['requests'] == ['/api/v1/service']


def test_unreachable_live_owner_is_not_reported_as_stopped(tmp_path):
    with ServeLock(tmp_path) as lock:
        result = inspect_local_server(home=tmp_path, database=lock.db_path,
                                      host='127.0.0.1', port=1, timeout=.1)
    assert result['state'] == 'degraded'
    assert result['reason'] == 'SERVICE_UNREACHABLE'
