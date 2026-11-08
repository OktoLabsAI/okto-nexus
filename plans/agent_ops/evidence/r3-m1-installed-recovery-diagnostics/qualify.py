"""Offline wheel qualification from a committed source archive, in a new prefix."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
COMMIT = '405cac3ffea92787b5c7d66c6ecb967f00624739'
SOURCE = ROOT / 'source'
PYTHON = ROOT / 'venv/Scripts/python.exe'
SITE = ROOT / 'venv/Lib/site-packages'
DEPENDENCIES = [
    ('nexus_connector_core', Path('C:/Users/jpamb/AppData/Local/Temp/core-dx43-observation-du1arc40/wheel/okto_nexus_connector_core-0.0.14-py3-none-any.whl'),
     '609e0fbbb20855c6b788d2523b0aeb6cdfbf4b3f5c9792c9e4a080284729c9dd'),
    ('okto_nexus_connector', Path('C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/native/wheels/okto_nexus_connector-0.0.12-py3-none-any.whl'),
     '73f1a3ba6daf1a4db6f98a9eaf7badaed0d32b151a30b4c0c6a0cf66c2eae1b5'),
]
TESTS = ['tests/test_embedded_recovery_diagnostics.py', 'tests/test_sqlite_writer_fairness.py',
         'tests/execution_r4/test_recovery_diagnostic_contention.py',
         'tests/execution_r4/test_terminal_connect.py']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, data):
    (ROOT / name).write_bytes((json.dumps(data, indent=2) + '\n').encode('utf-8'))


def environment():
    env = json.loads((ROOT / 'environment.json').read_text())
    env.update(OKTO_NEXUS_EMBEDDING_MODE='off', OKTO_NEXUS_DISABLE_HARNESS_DISCOVERY='1',
               OKTO_NEXUS_NO_BANNER='1', NO_PROXY='*',
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    return env


def run(name, argv, *, cwd=None):
    with (ROOT / (name + '.stdout.txt')).open('xb') as out, (ROOT / (name + '.stderr.txt')).open('xb') as err:
        child = subprocess.Popen(argv, cwd=cwd or ROOT, env=environment(), stdout=out, stderr=err,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        write(name + '-process.json', {'pid': child.pid, 'argv': argv, 'no_timeout_kill': True})
        print(json.dumps({'stage': name, 'pid': child.pid}), flush=True)
        code = child.wait()
    write(name + '-result.json', {'exit_code': code})
    if code:
        raise SystemExit(code)


def assert_snapshot():
    expected = json.loads((ROOT / 'snapshot-inputs.json').read_text())
    changed = [name for name, digest in expected.items()
               if not (SOURCE / name).is_file() or sha(SOURCE / name) != digest]
    assert not changed, changed
    return len(expected)


def products():
    record = json.loads((ROOT / 'wheel-result.json').read_text())
    return [('okto_nexus', Path(record['wheel']), record['sha256']), *DEPENDENCIES]


def package_proof(name):
    proof = {}
    for module, wheel, expected in products():
        assert sha(wheel) == expected
        files = {}
        with zipfile.ZipFile(wheel) as archive:
            payload = [item for item in archive.namelist() if item.startswith(module + '/') and not item.endswith('/')]
            for item in payload:
                raw = archive.read(item)
                assert (SITE / item).read_bytes() == raw, item
                if module == 'okto_nexus':
                    assert (SOURCE / 'src' / item).read_bytes() == raw, item
                files[item] = hashlib.sha256(raw).hexdigest()
            if module == 'okto_nexus':
                source_payload = {p.relative_to(SOURCE / 'src').as_posix()
                    for p in (SOURCE / 'src/okto_nexus').rglob('*')
                    if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
                assert source_payload == set(payload)
        proof[module] = {'wheel': str(wheel), 'sha256': expected,
                         'files': files, 'payload_count': len(files),
                         'source_compared': module == 'okto_nexus'}
    write(name, {'products': proof, 'total_payloads': sum(p['payload_count'] for p in proof.values()),
                 'snapshot_input_count': assert_snapshot(), 'snapshot_inputs_unchanged': True})
    return proof


def build():
    assert not SOURCE.exists() and not (ROOT / 'wheels').exists()
    for _, wheel, expected in DEPENDENCIES:
        assert sha(wheel) == expected
    archive = ROOT / 'source-snapshot.zip'
    run('git-archive', ['C:/Users/jpamb/AppData/Local/Microsoft/WinGet/Links/rtk.EXE', 'proxy',
        'C:/Program Files/Git/cmd/git.EXE', 'archive', '--format=zip', '-o', str(archive), COMMIT, '--',
        'pyproject.toml', 'README.md', 'LICENSE', 'uv.lock', 'src', 'tests', 'tools', 'vendor',
        'docs', 'frontend', '.github', 'plans/r4_execution', 'plans/contratos'], cwd=REPO)
    SOURCE.mkdir()
    with zipfile.ZipFile(archive) as data:
        for item in data.namelist():
            assert (SOURCE / item).resolve().is_relative_to(SOURCE)
        data.extractall(SOURCE)
    inputs = {p.relative_to(SOURCE).as_posix(): sha(p) for p in sorted(SOURCE.rglob('*')) if p.is_file()}
    write('snapshot-inputs.json', inputs)
    manifest = json.loads((SOURCE / 'vendor/ci/manifest.json').read_text())['artifacts']
    for entry, (_, wheel, expected) in zip(manifest, DEPENDENCIES, strict=True):
        assert entry['sha256'] == expected and sha(SOURCE / entry['path']) == expected
        assert (SOURCE / entry['path']).read_bytes() == wheel.read_bytes()
    (ROOT / 'wheels').mkdir()
    run('build', [str(PYTHON), '-I', '-B', '-m', 'pip', '--isolated', 'wheel', '--no-index',
                 '--no-deps', '--no-build-isolation', '--wheel-dir', str(ROOT / 'wheels'), str(SOURCE)])
    wheels = list((ROOT / 'wheels').glob('okto_nexus-*.whl'))
    assert len(wheels) == 1
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as data:
        payload = [name for name in data.namelist() if name.startswith('okto_nexus/') and not name.endswith('/')]
        for name in payload:
            assert (SOURCE / 'src' / name).read_bytes() == data.read(name)
    record = {'commit': COMMIT, 'source': str(SOURCE), 'snapshot_sha256': sha(archive),
              'snapshot_inputs': assert_snapshot(), 'wheel': str(wheel), 'sha256': sha(wheel),
              'nexus_payloads': len(payload), 'source_equals_wheel': True,
              'qualification': 'BUILT_OFFLINE_AWAITING_INSTALLED_TESTS'}
    write('wheel-result.json', record)
    print(json.dumps(record), flush=True)


def install():
    req = ROOT / 'requirements-products.txt'
    req.write_bytes(''.join(wheel.as_uri() + ' --hash=sha256:' + digest + '\n'
                           for _, wheel, digest in products()).encode('utf-8'))
    assert b'\r' not in req.read_bytes()
    run('install', [str(PYTHON), '-I', '-B', '-m', 'pip', '--isolated', 'install', '--no-index',
                    '--no-deps', '--require-hashes', '-r', str(req)])
    run('pip-check', [str(PYTHON), '-I', '-B', '-m', 'pip', '--isolated', 'check'])
    package_proof('package-proof-before.json')
    probe = """import importlib,json,sys
from pathlib import Path
modules = ['okto_nexus','nexus_connector_core','okto_nexus_connector',
 'okto_nexus.bootstrap.embedded_agent_recovery','okto_nexus.adapters.outbound.sqlite.diagnostics',
 'okto_nexus.adapters.outbound.sqlite.write_gate','okto_nexus.application.terminal_connection']
paths={name: str(Path(importlib.import_module(name).__file__).resolve()) for name in modules}
assert all(Path(path).is_relative_to(Path(sys.prefix)) and 'site-packages' in path for path in paths.values())
assert not any('source/src' in path.replace('\\\\','/') for path in sys.path)
print(json.dumps({'python':sys.executable,'base_python':sys._base_executable,'prefix':sys.prefix,
 'isolated':sys.flags.isolated,'modules':paths,'sys_path':sys.path},indent=2))
"""
    run('import-proof', [str(PYTHON), '-I', '-B', '-c', probe])
    print(json.dumps({'installed': True, 'package_proof': str(ROOT / 'package-proof-before.json')}), flush=True)


def test():
    package_proof('package-proof-test-entry.json')
    run('installed-tests', [str(PYTHON), '-I', '-B', '-X', 'utf8', str(SOURCE / 'tools/ci_installed.py'),
        'test', '--wheel', str(products()[0][1]), '--output', str(ROOT / 'canonical'), '--tests', *TESTS])
    package_proof('package-proof-after.json')
    run('pip-check-after', [str(PYTHON), '-I', '-B', '-m', 'pip', '--isolated', 'check'])
    report = json.loads((ROOT / 'canonical/campaign.json').read_text())
    assert report['status'] == 'PASS' and report['exit_code'] == 0 and report['changed_inputs'] == []
    print(json.dumps({'status': 'PASS', 'campaign': str(ROOT / 'canonical/campaign.json'),
                      'snapshot_inputs_unchanged': True, 'payloads_unchanged': True}), flush=True)


if __name__ == '__main__':
    {'build': build, 'install': install, 'test': test}[sys.argv[1]]()
