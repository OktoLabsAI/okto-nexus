"""Install only the three reviewed wheels into this already isolated environment."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCE = Path('C:\\Users\\jpamb\\AppData\\Local\\Temp\\m1-v12-bundle-bldo9qy7\\successor14\\work-revision15\\package\\built-wheels')
WHEELS = {'okto_nexus-0.3.3-py3-none-any.whl': '9804124472277f92c69b0a4b0840a62e8cf3c3baa185509f3cf58ba62e856437', 'okto_nexus_connector-0.0.12-py3-none-any.whl': 'f9864f13db4c5e6e5afdfd8f28ca5384512a17a1f8efb1897cb3a4d810d43cf4', 'okto_nexus_connector_core-0.0.14-py3-none-any.whl': 'd881ab35ac619147df51cbe3a10964e534c50acd117e45e2612dcec7fbc1afe9'}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name, value):
    with (ROOT / name).open('x', encoding='utf-8') as out:
        json.dump(value, out, indent=2); out.write('\n'); out.flush(); os.fsync(out.fileno())

assert not (ROOT / 'installation.json').exists()
assert json.loads((ROOT / 'dependency-preparation.json').read_bytes())['status'] == 'DEPENDENCIES_ONLY_READY'
(ROOT / 'wheels').mkdir()
for name, digest in WHEELS.items():
    assert sha(SOURCE / name) == digest
    shutil.copyfile(SOURCE / name, ROOT / 'wheels' / name)
    assert sha(ROOT / 'wheels' / name) == digest
python = ROOT / 'venv/Scripts/python.exe'
env = json.loads((ROOT / 'environment.json').read_bytes())
def run(name, args):
    with (ROOT / (name + '.stdout')).open('xb') as stdout, (ROOT / (name + '.stderr')).open('xb') as stderr:
        child = subprocess.Popen([str(python), '-I', '-B', '-X', 'utf8', *args], cwd=ROOT,
            env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        code = child.wait()
    assert code == 0, name + '_FAILED_RETAIN_OUTPUTS'
    return {'returncode': code, 'stdout_sha256': sha(ROOT / (name + '.stdout')), 'stderr_sha256': sha(ROOT / (name + '.stderr'))}
install = run('install', ['-m', 'pip', 'install', '--no-index', '--no-deps', '--disable-pip-version-check',
    *[str(ROOT / 'wheels' / name) for name in WHEELS]])
check = run('pip-check', ['-m', 'pip', 'check', '--disable-pip-version-check'])
site = ROOT / 'venv/Lib/site-packages'
files = []
for name in WHEELS:
    with zipfile.ZipFile(ROOT / 'wheels' / name) as wheel:
        for member in wheel.namelist():
            if member.endswith('/') or member.endswith('.dist-info/RECORD'):
                continue
            target = site / member
            assert target.is_relative_to(site) and not target.is_symlink()
            raw = wheel.read(member)
            assert target.read_bytes() == raw, member
            files.append({'path': str(target), 'sha256': sha(target), 'wheel': name})
images = {str(p.resolve()): sha(p) for p in [python, ROOT / 'venv/Scripts/pythonw.exe',
    Path('C:/Python313/python.exe'), Path('C:/Python313/pythonw.exe')]}
save('installation.json', {'status': 'INSTALLED_VERIFIED', 'python': str(python), 'python_prefix': str(ROOT / 'venv'),
    'wheels': {name: {'path': str(ROOT / 'wheels' / name), 'sha256': digest} for name, digest in WHEELS.items()},
    'files': files, 'payload_count': len(files), 'python_images': images, 'install': install, 'pip_check': check,
    'dependency_manifest_sha256': sha(ROOT / 'dependency-manifest.json'), 'services_started': 0,
    'provider_calls': 0, 'historical_environment_mutated': False})
print(json.dumps({'status': 'INSTALLED_VERIFIED', 'payloads': len(files), 'manifest_sha256': sha(ROOT / 'installation.json')}))
