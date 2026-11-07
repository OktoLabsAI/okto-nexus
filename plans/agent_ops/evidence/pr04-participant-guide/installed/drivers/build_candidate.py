"""Build an immutable DX04 installed candidate entirely outside the checkout."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parent
REPO = Path(sys.argv[1]).resolve()
DEST = ROOT / sys.argv[2]
DEST.mkdir(exist_ok=False)
PACKAGE = REPO / 'src/okto_nexus'
CORE = REPO / 'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'
BUNDLE = 'adapters/inbound/http/static/assets/index-Baw-pvQn.js'
BUNDLE_SHA = '15d170828f24b24417570aa0bf13852d7efe0c9efe45a9bd80d966ebcf4ece2b'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(directory):
    return {p.relative_to(directory).as_posix(): digest(p.read_bytes()) for p in sorted(directory.rglob('*'))
        if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}


def run(command, name):
    env = {key: value for key, value in os.environ.items()
        if not key.upper().startswith(('PYTHON', 'PYTEST', 'OKTO_NEXUS', 'NEXUS_'))}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    with (DEST / name).open('x', encoding='utf-8') as log:
        subprocess.run(command, cwd=DEST, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)


before = inventory(PACKAGE)
assert before[BUNDLE] == BUNDLE_SHA, 'The frozen canonical dashboard bundle changed.'
version = tomllib.loads((REPO / 'pyproject.toml').read_text())['project']['version']
stage = DEST / 'build-source'
stage.mkdir()
for name in ('pyproject.toml', 'README.md', 'LICENSE', 'LICENSE.md', 'MANIFEST.in'):
    if (REPO / name).is_file():
        shutil.copy2(REPO / name, stage / name)
shutil.copytree(PACKAGE, stage / 'src/okto_nexus', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
assert inventory(stage / 'src/okto_nexus') == before
run([sys.executable, '-m', 'build', '--wheel', '--no-isolation', '--outdir', str(DEST / 'wheels'), str(stage)], 'build.log')
wheel, = (DEST / 'wheels').glob('okto_nexus-' + version + '-*.whl')
run([sys.executable, '-I', '-m', 'venv', '--system-site-packages', str(DEST / 'venv')], 'venv.log')
python = DEST / 'venv/Scripts/python.exe'
run([str(python), '-I', '-m', 'pip', '--isolated', 'install', '--ignore-installed', '--no-deps', '--no-index',
    str(CORE), str(wheel)], 'install.log')
installed = DEST / 'venv/Lib/site-packages/okto_nexus'
with zipfile.ZipFile(wheel) as archive:
    packaged = {name[len('okto_nexus/'):]: digest(archive.read(name)) for name in archive.namelist()
        if name.startswith('okto_nexus/') and not name.endswith('/')}
assert before == inventory(PACKAGE) == packaged == inventory(installed), 'Source/package byte or set drift.'
proof = dict(revision=1, source_root=str(REPO), build_source=str(stage), version=version,
    wheel=str(wheel), wheel_sha256=digest(wheel.read_bytes()), core_wheel=str(CORE),
    core_sha256=digest(CORE.read_bytes()), python=str(python), installed_package=str(installed),
    exact_source_stage_wheel_installed=True, file_count=len(before), files=before,
    dashboard_bundle=BUNDLE, dashboard_sha256=BUNDLE_SHA,
    pyproject_sha256=digest((REPO / 'pyproject.toml').read_bytes()))
with (DEST / 'package-proof.json').open('x', encoding='utf-8') as output:
    json.dump(proof, output, indent=2)
print(json.dumps({key: value for key, value in proof.items() if key != 'files'}, indent=2))
