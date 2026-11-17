"""Prepare one persistible regression file outside the frozen repository tests."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
gate = Path(json.loads((HERE / 'gate-allocation.json').read_text())['root'])
root = Path(tempfile.mkdtemp(prefix='nexus-qc-compat-regression-')).resolve()
target = root / 'test_entry_compatibility.py'
text = (gate / 'after/tests/test_gate_derivative.py').read_text(encoding='utf-8')
text = '''"""Public/legacy entry routing and exact HTTP capability diagnostics.

All networking is bounded loopback owned by the test. No Server, account,
vault, native harness, setup Test or provider is started.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
''' + text
text += '''

from okto_nexus.adapters.inbound.cli.quick_connect_ids import require_public_ids
from okto_nexus.adapters.outbound.operator_client import RemoteOperatorHTTP
from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP


def operator_transport(kind, port):
    if kind == 'remote':
        transport = RemoteOperatorHTTP(f'http://127.0.0.1:{port}')
        transport.timeout = 1
        return transport
    return LocalOperatorHTTP(host='127.0.0.1', port=port, timeout=1)


@pytest.mark.parametrize('kind', ['local', 'remote'])
@pytest.mark.parametrize('status,error_code,malformed,expected', [
    (404, None, False, 'CONNECT_ID_UNSUPPORTED_SERVER'),
    (405, None, False, 'CONNECT_ID_UNSUPPORTED_SERVER'),
    (404, None, True, 'CONNECT_ID_UNSUPPORTED_SERVER'),
    (401, 'AUTH_FAILED', False, 'AUTH_FAILED'),
    (403, 'PERMISSION_DENIED', False, 'PERMISSION_DENIED'),
    (403, 'HTTP_ERROR', False, 'HTTP_ERROR'),
    (403, None, False, 'REQUEST_REFUSED'),
    (500, 'HTTP_ERROR', False, 'HTTP_ERROR'),
])
def test_public_id_http_status_is_precise(kind, status, error_code, malformed, expected):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.command, self.path))
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            value = {'error': {'code': error_code}} if error_code else {'detail': 'refused'}
            self.wfile.write(b'bad' if malformed else json.dumps(value).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        transport = operator_transport(kind, server.server_port)
        route = '/api/v1/runtime-management/connections/public-ids'
        with pytest.raises(ConnectionError) as raw:
            transport('GET', route)
        assert raw.value.http_status == status
        assert raw.value.possible_effect is False
        with pytest.raises(ConnectionError) as refusal:
            require_public_ids(transport, 'own-test-server')
        if kind == 'remote' and expected == 'AUTH_FAILED':
            expected = 'OPERATOR_LOGIN_REQUIRED'
        assert refusal.value.code == expected
        assert refusal.value.possible_effect is False
        if expected != 'CONNECT_ID_UNSUPPORTED_SERVER':
            assert refusal.value.http_status == status
        assert calls == [('GET', route), ('GET', route)]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


@pytest.mark.parametrize('kind', ['local', 'remote'])
def test_public_id_network_refusal_is_not_unsupported(kind):
    # Keep the port bound but not listening, so another fixture cannot claim it.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        transport = operator_transport(kind, sock.getsockname()[1])
        with pytest.raises(ConnectionError) as refusal:
            require_public_ids(transport, 'own-test-server')
    assert refusal.value.code == 'SERVER_UNREACHABLE'
    assert refusal.value.http_status is None
    assert refusal.value.possible_effect is False
'''
ast.parse(text)
target.write_text(text, encoding='utf-8', newline='\n')
report = dict(root=str(root), test_file=str(target), proposed_repository_path='tests/quick_connect/test_entry_compatibility.py',
    scenarios=dict(gate=32, http=16, network=2, total=50), executed=False,
    originals_unchanged=['tests/execution_r4/test_connection_catalog.py', 'tests/execution_r4/test_terminal_multi_harness.py'],
    sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    plan=['Apply reviewed I02 and gate product patches after input freeze.',
        'Copy this file into tests/quick_connect without editing the three legacy nodes.',
        'Build a fresh wheel and install into a new owned prefix; preserve 0s9 and all older prefixes.',
        'Copy quick_connect fixtures/helpers without checkout src and run the whole quick_connect directory plus the three legacy nodes under -I -B.',
        'Record installed module origins, wheel/payload equality, commands, JUnit, source/input pins and owned cleanup.',
        'Do not repeat old-Server HTTP proof, provider/native campaign, or unrelated broad suite.'])
(HERE / 'persistent-regression-plan.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
