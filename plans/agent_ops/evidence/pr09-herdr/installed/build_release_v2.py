"""Build and qualify a detached, non-editable release without modifying checkout."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent / 'qualified-v2'
ROOT.mkdir(exist_ok=False)
REPO = Path(sys.argv[1]).resolve()
PACKAGE = REPO / 'src' / 'okto_nexus'
CORE = REPO / 'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def relevant(name):
    return '__pycache__' not in Path(name).parts and not name.endswith(('.pyc', '.pyo'))


def inventory(directory):
    return {path.relative_to(directory).as_posix(): sha(path.read_bytes())
            for path in sorted(directory.rglob('*'))
            if path.is_file() and relevant(path.relative_to(directory).as_posix())}


def run(command, log):
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(('PYTHON', 'PYTEST', 'OKTO_NEXUS', 'NEXUS_'))}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    with (ROOT / log).open('x', encoding='utf-8') as output:
        subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)


before = inventory(PACKAGE)
previous_path = ROOT.parent / 'qualified/package-proof.json'
previous = json.loads(previous_path.read_text(encoding='utf-8'))
previous_files = {name: item['source_sha256'] for name, item in previous['files'].items()}
assert set(before) == set(previous_files), 'Unexpected added/removed package files in the targeted V2 release.'
changed_files = sorted(name for name, digest in before.items() if digest != previous_files[name])
assert changed_files == ['adapters/outbound/observation/herdr.py'], changed_files
server_import_path = ROOT.parent / 'qualified/server-import-proof.json'
server_import = json.loads(server_import_path.read_text(encoding='utf-8'))
assert 'okto_nexus.adapters.outbound.observation.herdr' not in server_import['modules']
assert sha(Path(previous['wheel']).read_bytes()) == previous['wheel_sha256']
core_digest = sha(CORE.read_bytes())
metadata_digest = sha((REPO / 'pyproject.toml').read_bytes())
staging = ROOT / 'build-source'
staging.mkdir()
for name in ('pyproject.toml', 'README.md', 'LICENSE', 'LICENSE.md', 'MANIFEST.in'):
    if (REPO / name).is_file():
        shutil.copy2(REPO / name, staging / name)
shutil.copytree(PACKAGE, staging / 'src/okto_nexus', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
assert inventory(staging / 'src/okto_nexus') == before, 'Detached copy differs.'
run([sys.executable, '-m', 'build', '--wheel', '--no-isolation', '--outdir', str(ROOT / 'release'), str(staging)], 'wheel-build.log')
wheel, = (ROOT / 'release').glob('okto_nexus-0.3.3-*.whl')
run([sys.executable, '-I', '-m', 'venv', '--system-site-packages', str(ROOT / 'venv')], 'venv-create.log')
python = ROOT / 'venv/Scripts/python.exe'
run([str(python), '-I', '-m', 'pip', '--isolated', 'install', '--ignore-installed', '--no-deps', '--no-index', str(CORE), str(wheel)], 'wheel-install.log')
installed = ROOT / 'venv/Lib/site-packages/okto_nexus'
with zipfile.ZipFile(wheel) as archive:
    wheel_files = {name[len('okto_nexus/'):]: sha(archive.read(name))
                   for name in archive.namelist() if name.startswith('okto_nexus/')
                   and not name.endswith('/') and relevant(name[len('okto_nexus/'):])}
after, installed_files = inventory(PACKAGE), inventory(installed)
assert sha(CORE.read_bytes()) == core_digest
assert sha((REPO / 'pyproject.toml').read_bytes()) == metadata_digest
assert before == after, 'Source changed while building; do not qualify this release.'
assert before == wheel_files == installed_files, 'Source/wheel/installed sets or raw bytes differ.'
proof = {
    'revision': 2, 'inventory': 'all package files except Python caches',
    'pyproject_sha256': metadata_digest, 'source_root': str(REPO), 'build_source': str(staging),
    'wheel': str(wheel), 'wheel_sha256': sha(wheel.read_bytes()),
    'core_wheel': str(CORE), 'core_wheel_sha256': sha(CORE.read_bytes()),
    'installed_package': str(installed), 'python': str(python),
    'source_unchanged_during_build': True, 'exact_relative_sets_equal': True,
    'all_raw_bytes_equal': True,
    'counts': {'python': sum(n.endswith('.py') for n in before),
               'migrations': sum(n.startswith('migrations/') for n in before),
               'static': sum(n.startswith('adapters/inbound/http/static/') for n in before),
               'total': len(before)},
    'files': {name: {'source_sha256': digest, 'wheel_sha256': wheel_files[name],
                     'installed_sha256': installed_files[name]} for name, digest in before.items()},
}
proof['previous_release'] = {
    'proof': str(previous_path), 'proof_sha256': sha(previous_path.read_bytes()),
    'wheel_sha256': previous['wheel_sha256'], 'changed_files': changed_files,
    'unchanged_file_count': len(before) - len(changed_files),
    'server_import_proof': str(server_import_path),
    'server_import_proof_sha256': sha(server_import_path.read_bytes()),
    'server_scope': 'The retained V1 Server does not import the changed optional observer CLI transport; every other package byte is identical.'}
(ROOT / 'package-proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in proof.items() if k != 'files'}, indent=2))
