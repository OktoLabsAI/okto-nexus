"""Build a detached candidate and compare every packaged source byte."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

# Preserve the initial checkout-venv failure (setuptools absent) separately.
ROOT = Path(__file__).resolve().parent / 'candidate-v2'
ROOT.mkdir(exist_ok=False)
REPO = Path(sys.argv[1]).resolve()
PACKAGE = REPO / 'src/okto_nexus'
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
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(('PYTHON', 'PYTEST', 'OKTO_NEXUS', 'NEXUS_'))}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    with (ROOT / log).open('x', encoding='utf-8') as output:
        subprocess.run(command, cwd=ROOT, env=env, stdout=output,
                       stderr=subprocess.STDOUT, check=True)


before = inventory(PACKAGE)
core_digest = sha(CORE.read_bytes())
metadata_digest = sha((REPO / 'pyproject.toml').read_bytes())
staging = ROOT / 'build-source'
staging.mkdir()
for name in ('pyproject.toml', 'README.md', 'LICENSE', 'LICENSE.md', 'MANIFEST.in'):
    if (REPO / name).is_file():
        shutil.copy2(REPO / name, staging / name)
shutil.copytree(PACKAGE, staging / 'src/okto_nexus', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
assert inventory(staging / 'src/okto_nexus') == before
run([sys.executable, '-m', 'build', '--wheel', '--no-isolation', '--outdir', str(ROOT / 'release'), str(staging)], 'wheel-build.log')
wheel, = (ROOT / 'release').glob('okto_nexus-0.3.3-*.whl')
run([sys.executable, '-I', '-m', 'venv', '--system-site-packages', str(ROOT / 'venv')], 'venv-create.log')
python = ROOT / 'venv/Scripts/python.exe'
run([str(python), '-I', '-m', 'pip', '--isolated', 'install', '--ignore-installed', '--no-deps',
     '--no-index', str(CORE), str(wheel)], 'wheel-install.log')
installed = ROOT / 'venv/Lib/site-packages/okto_nexus'
with zipfile.ZipFile(wheel) as archive:
    wheel_files = {name[len('okto_nexus/'):]: sha(archive.read(name))
                   for name in archive.namelist() if name.startswith('okto_nexus/')
                   and not name.endswith('/') and relevant(name[len('okto_nexus/'):])}
after, installed_files = inventory(PACKAGE), inventory(installed)
assert sha(CORE.read_bytes()) == core_digest
assert sha((REPO / 'pyproject.toml').read_bytes()) == metadata_digest
assert before == after, 'Source changed during build.'
assert before == wheel_files == installed_files, 'Source/wheel/installed bytes differ.'
proof = dict(source_root=str(REPO), build_source=str(staging), wheel=str(wheel),
    wheel_sha256=sha(wheel.read_bytes()), core_wheel=str(CORE), core_wheel_sha256=core_digest,
    pyproject_sha256=metadata_digest, installed_package=str(installed), python=str(python),
    source_unchanged_during_build=True, exact_relative_sets_equal=True, all_raw_bytes_equal=True,
    counts=dict(python=sum(n.endswith('.py') for n in before),
        migrations=sum(n.startswith('migrations/') for n in before),
        static=sum(n.startswith('adapters/inbound/http/static/') for n in before), total=len(before)),
    files={name: dict(source_sha256=digest, wheel_sha256=wheel_files[name],
                     installed_sha256=installed_files[name]) for name, digest in before.items()})
(ROOT / 'package-proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in proof.items() if key != 'files'}, indent=2))
