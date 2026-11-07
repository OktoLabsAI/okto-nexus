"""Four exact installed client/Server pairs over loopback public HTTP only."""
from pathlib import Path
import hashlib
import json
import subprocess
import time

ROOT = Path(__file__).resolve().parent
OLD = ROOT / 'old-venv/Scripts/python.exe'
NEW = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ci-connector-refresh-la1tb1l6/venv/Scripts/python.exe')
NEXUS = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
env = json.loads((ROOT / 'environment.json').read_text(encoding='utf-8'))
output = ROOT / 'matrix'
output.mkdir()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, label):
    with (output / (label + '.log')).open('wb') as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=60)
    assert result.returncode == 0, (label, result.returncode)


def artifacts(old):
    if old:
        wheels = ROOT / 'wheels'
        specs = [('okto_nexus', wheels / 'okto_nexus-0.3.2-py3-none-any.whl', 'nexus'),
                 ('nexus_connector_core', wheels / 'okto_nexus_connector_core-0.0.13-py3-none-any.whl', None),
                 ('okto_nexus_connector', wheels / 'okto_nexus_connector-0.0.11-py3-none-any.whl', 'connector')]
    else:
        specs = [('okto_nexus', Path('C:/Users/jpamb/AppData/Local/Temp/dx04-mcp-guide-installed-sk13m28a/candidate-v1/wheels/okto_nexus-0.3.3-py3-none-any.whl'), None),
                 ('nexus_connector_core', NEXUS / 'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl', None),
                 ('okto_nexus_connector', NEXUS / 'vendor/ci/okto_nexus_connector-0.0.12-py3-none-any.whl', None)]
    return [dict(module=module, wheel=str(path), sha256=sha(path),
                 **({'source': str(ROOT / 'build-source' / source / 'src')} if source else {}))
            for module, path, source in specs]


def main():
    for label, python in [('old', OLD), ('new', NEW)]:
        spec = dict(artifacts=artifacts(label == 'old'),
                    expected_package_root=str(python.parent.parent / 'Lib/site-packages'),
                    output=str(output / (label + '-installed.json')))
        path = output / (label + '-artifact-spec.json')
        path.write_text(json.dumps(spec, indent=2) + '\n', encoding='utf-8')
        run([str(python), '-I', '-X', 'utf8', str(ROOT / 'verify_installed.py'), str(path)], label + '-verify')
        run([str(python), '-I', '-m', 'pip', 'check'], label + '-pipcheck')
    results = []
    for server_label, server_python in [('old', OLD), ('new', NEW)]:
        server_root = output / (server_label + '-server')
        log = (output / (server_label + '-server.log')).open('wb')
        command = [str(server_python), '-I', '-X', 'utf8', str(ROOT / 'server_probe.py'), str(server_root)]
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            until = time.monotonic() + 40
            while not (server_root / 'ready.json').exists():
                assert process.poll() is None, ('server_start_failed', server_label, process.returncode)
                assert time.monotonic() < until, ('server_start_timeout', server_label)
                time.sleep(.05)
            ready = json.loads((server_root / 'ready.json').read_text(encoding='utf-8'))
            assert ready['pid'] == process.pid
            for client_label, client_python in [('old', OLD), ('new', NEW)]:
                label = client_label + '-client--' + server_label + '-server'
                report = output / (label + '.json')
                run([str(client_python), '-I', '-X', 'utf8', str(ROOT / 'client_probe.py'),
                     ready['url'], str(report)], label)
                result = json.loads(report.read_text(encoding='utf-8'))
                if client_label == server_label:
                    assert result['state'] == 'compatible' and result['protocol']['remote_execution_ready'] is True
                else:
                    assert result['state'] == 'refused' and result['code'] == 'VERSION_INCOMPATIBLE'
                    assert result['stage'] == 'protocol' and result['possible_effect'] is False
                results.append(dict(pair=label, **result))
        finally:
            if server_root.exists():
                (server_root / 'stop').write_text('stop owned HTTP fixture\n', encoding='utf-8')
            try:
                code = process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                code = process.wait(timeout=10)
                raise AssertionError('Owned HTTP fixture did not stop normally')
            finally:
                log.close()
            (output / (server_label + '-cleanup.json')).write_text(json.dumps({
                'pid': process.pid, 'exit_code': code, 'exited': process.poll() is not None,
                'normal_control': 'private stop-file, graceful uvicorn exit; no service registered',
            }, indent=2) + '\n', encoding='utf-8')
        assert code == 0, (server_label, code)
        proof = json.loads((server_root / 'proof.json').read_text(encoding='utf-8'))
        assert proof['changed_tables'] == [] and proof['all_requests_public_uncredentialed'] is True
        assert len(proof['requests']) == 2
    summary = {'status': 'PASS', 'pair_count': len(results), 'pairs': results,
               'providers_used': False, 'credentials_supplied': False,
               'daemon_lifecycle_exercised': False, 'native_services_registered': False,
               'qualification': 'Public protocol negotiation only; compatible does not assert authenticated work readiness.'}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'root': str(ROOT), 'status': 'PASS', 'pairs': len(results)}))


if __name__ == '__main__':
    main()
