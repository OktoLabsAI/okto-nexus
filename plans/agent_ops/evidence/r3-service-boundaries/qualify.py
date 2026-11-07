from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import zipfile

root = Path(__file__).parent
snapshot = root / 'snapshot'
python = root / 'venv/Scripts/python.exe'
wheel = next((root / 'wheels').glob('*.whl'))
reports = root / 'reports'
reports.mkdir(exist_ok=True)
manifest = json.loads((snapshot / 'vendor/ci/manifest.json').read_text())
dependencies = [snapshot / item['path'] for item in manifest['artifacts']]
env = {k: v for k, v in os.environ.items() if k.upper() in {
    'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP'}}
env['SystemRoot'] = os.environ['SYSTEMROOT']
for name in ('USERPROFILE', 'APPDATA', 'LOCALAPPDATA'):
    directory = root / 'isolated-env' / name.lower()
    directory.mkdir(parents=True, exist_ok=True)
    env[name] = str(directory)
env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', OKTO_NEXUS_NO_BANNER='1',
           SVC_EVIDENCE_DIR=str(reports))

def run(name, command):
    with (reports / (name + '.txt')).open('wb') as log:
        result = subprocess.run(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT)
    print(json.dumps({'step': name, 'exit': result.returncode}), flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)

run('install', [str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
    str(wheel) + '[serve-lite,dev]', str(dependencies[0]), str(dependencies[1]) + '[test]',
    'mcp==1.30.0'])
run('pip-check', [str(python), '-m', 'pip', 'check'])
proof = {}
for artifact, module in zip([wheel, *dependencies],
                            ['okto_nexus', 'nexus_connector_core', 'okto_nexus_connector']):
    with zipfile.ZipFile(artifact) as archive:
        names = [n for n in archive.namelist() if n.startswith(module + '/') and not n.endswith('/')]
        for name in names:
            assert (root / 'venv/Lib/site-packages' / name).read_bytes() == archive.read(name), name
            if module == 'okto_nexus':
                assert (snapshot / 'src' / name).read_bytes() == archive.read(name), name
        proof[module] = {'wheel': str(artifact), 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                         'installed_files': len(names), 'source_compared': module == 'okto_nexus'}
(reports / 'package-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
(reports / 'environment.json').write_text(json.dumps({'forwarded_names': sorted(env),
    'personal_profile_forwarded': False, 'provider_credentials_forwarded': False,
    'native_service_registration': False}, indent=2) + '\n')
run('tests', [str(python), '-I', '-X', 'utf8', str(snapshot / 'tools/ci_installed.py'),
    'test', '--wheel', str(wheel), '--output', str(reports / 'installed'), '--tests',
    'tests/test_service_failure_boundaries.py', 'tests/test_service_bind_diagnostics.py',
    'tests/test_service_logs.py',
    'tests/test_serve_lock.py::test_failed_bootstrap_releases_both_locks',
    'tests/test_serve_lock.py::test_unavailable_lock_storage_reports_failure_without_bootstrap'])
