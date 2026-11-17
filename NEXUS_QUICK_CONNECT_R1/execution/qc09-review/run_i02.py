"""Actual old-Server refusal plus bounded loopback transport negatives."""
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / 'i02-allocation.json').read_text())['root']).resolve()
PREFIX = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-0s9w2_3_/venv')
OLD = Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r3-harness-pr27-gsg_twh1/venv/Scripts/python.exe')
assert Path(sys.prefix).resolve() == PREFIX.resolve()
sys.path.insert(0, str(ROOT / 'overlay'))
from okto_nexus.adapters.inbound.cli.quick_connect_ids import require_public_ids
from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
from okto_nexus.adapters.outbound.operator_client import RemoteOperatorHTTP
from okto_nexus.application.terminal_connection import ConnectionError
import okto_nexus
assert Path(okto_nexus.__file__).resolve().is_relative_to(ROOT / 'overlay')


def caught(function):
    try:
        function()
    except ConnectionError as error:
        return dict(code=error.code, http_status=error.http_status, possible_effect=error.possible_effect)
    raise AssertionError('Expected a bounded refusal')


def main():
    assert not (ROOT / 'qualification.json').exists()
    checks = []
    class Handler(BaseHTTPRequestHandler):
        status, error_code, malformed = 404, None, False

        def do_GET(self):
            self.send_response(self.status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'bad' if self.malformed else json.dumps(
                {'error': {'code': self.error_code}} if self.error_code else {'detail': 'refused'}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for transport in (LocalOperatorHTTP(host='127.0.0.1', port=server.server_port, timeout=1),
                RemoteOperatorHTTP(f'http://127.0.0.1:{server.server_port}')):
            transport.timeout = 1
            for status, code, malformed, expected in (
                (404, None, False, 'CONNECT_ID_UNSUPPORTED_SERVER'),
                (405, None, False, 'CONNECT_ID_UNSUPPORTED_SERVER'),
                (404, None, True, 'CONNECT_ID_UNSUPPORTED_SERVER'),
                (401, 'AUTH_FAILED', False, 'OPERATOR_LOGIN_REQUIRED' if isinstance(transport, RemoteOperatorHTTP) else 'AUTH_FAILED'),
                (403, 'PERMISSION_DENIED', False, 'PERMISSION_DENIED'),
                (403, 'HTTP_ERROR', False, 'HTTP_ERROR'),
                (403, None, False, 'REQUEST_REFUSED'),
                (500, 'HTTP_ERROR', False, 'HTTP_ERROR'),
            ):
                Handler.status, Handler.error_code, Handler.malformed = status, code, malformed
                result = caught(lambda: require_public_ids(transport, 'own-test-server'))
                assert result['code'] == expected, result
                if expected != 'CONNECT_ID_UNSUPPORTED_SERVER':
                    assert result['http_status'] == status
                assert result['possible_effect'] is False
                checks.append(dict(transport=type(transport).__name__, status=status, error_code=code,
                    malformed=malformed, result=result))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        unused = sock.getsockname()[1]
    for transport in (LocalOperatorHTTP(host='127.0.0.1', port=unused, timeout=1),
            RemoteOperatorHTTP(f'http://127.0.0.1:{unused}')):
        transport.timeout = 1
        result = caught(lambda: require_public_ids(transport, 'own-test-server'))
        assert result == dict(code='SERVER_UNREACHABLE', http_status=None, possible_effect=False)
        checks.append(dict(transport=type(transport).__name__, network='closed-own-port', result=result))
    for code in ('NOT_FOUND', 'HTTP_ERROR', 'VALIDATION_ERROR'):
        def legacy(*args):
            raise ConnectionError(code, 'own legacy error')
        result = caught(lambda: require_public_ids(legacy, 'own-test-server'))
        assert result['code'] == 'CONNECT_ID_UNSUPPORTED_SERVER'
        checks.append(dict(legacy_code=code, result=result))

    project, empty = ROOT / 'project', ROOT / 'empty-path'
    project.mkdir()
    empty.mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() in (
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PROCESSOR_ARCHITECTURE',
        'NUMBER_OF_PROCESSORS', 'PATHEXT')}
    for name in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP'):
        path = ROOT / ('env-' + name.lower())
        path.mkdir()
        env[name] = str(path)
    env.update(PATH=str(empty), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
        OKTO_NEXUS_NO_BANNER='1', OKTO_NEXUS_LOG_LEVEL='warning')
    home = ROOT / 'old-server-home'
    serve = [str(OLD), '-I', '-B', '-m', 'okto_nexus.adapters.inbound.cli.main', 'serve',
        '--home', str(home), '--project-root', str(project), '--host', '127.0.0.1',
        '--port', str(unused), '--embedding-mode', 'off']
    process = None
    cleanup = None
    try:
        with (ROOT / 'old-server.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen(serve, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 30
            transport = LocalOperatorHTTP(host='127.0.0.1', port=unused, timeout=1)
            while True:
                assert process.poll() is None, 'Owned Server exited before readiness'
                try:
                    me = transport('GET', '/api/v1/runtime-management/connections/me')
                    break
                except ConnectionError:
                    assert time.monotonic() < deadline, 'Readiness deadline'
                    time.sleep(0.1)
            direct = caught(lambda: transport('GET', '/api/v1/runtime-management/connections/public-ids'))
            assert direct == dict(code='REQUEST_REFUSED', http_status=404, possible_effect=False), direct
            refusal = caught(lambda: require_public_ids(transport, me['server_id']))
            assert refusal['code'] == 'CONNECT_ID_UNSUPPORTED_SERVER', refusal
            checks.append(dict(actual_old_server='0.3.5 installed PR27', me_status=200,
                direct=direct, capability_refusal=refusal))
    finally:
        if process is not None:
            stop = [str(OLD), '-I', '-B', '-m', 'okto_nexus.adapters.inbound.cli.main', 'service', 'stop',
                '--home', str(home), '--host', '127.0.0.1', '--port', str(unused), '--timeout', '15', '--json']
            result = subprocess.run(stop, cwd=ROOT, env=env, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=25, check=False)
            (ROOT / 'stop.stdout.json').write_text(result.stdout, encoding='utf-8')
            (ROOT / 'stop.stderr.txt').write_text(result.stderr, encoding='utf-8')
            code = process.wait(timeout=15)
            cleanup = dict(canonical_exit=result.returncode, physical_exit=code, pid=process.pid, forced=False)
            assert result.returncode == code == 0
    site = PREFIX / 'Lib/site-packages/okto_nexus'
    before = json.loads((ROOT / 'installed-before.json').read_text())
    after = {p.relative_to(site).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in site.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    assert before == after
    with socket.socket() as sock:
        assert sock.connect_ex(('127.0.0.1', unused)) != 0
    report = dict(at=datetime.now(timezone.utc).isoformat(), status='PASS_DERIVATIVE_ONLY',
        root=str(ROOT), command=[sys.executable, '-I', '-B', str(Path(__file__).resolve())],
        overlay_origin=okto_nexus.__file__, installed_prefix=str(PREFIX), installed_files=len(after),
        installed_drift=[], checks=checks, cleanup=cleanup, provider_calls=0,
        limitations=['Derivative overlay is not the shipped installed candidate.',
            'No new Server upgrade or provider work executed.', 'CI inputs, source, and installed prefix unchanged.'])
    (ROOT / 'qualification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(dict(root=str(ROOT), checks=len(checks), cleanup=cleanup, installed_drift=[])), flush=True)


if __name__ == '__main__':
    main()
