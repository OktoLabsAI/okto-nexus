"""Build detached Nexus/Connector wheels and compare exact source/install bytes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent / sys.argv[1]
ROOT.mkdir(exist_ok=False)
NEXUS = Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
CONNECTOR = NEXUS.parent / 'okto-nexus-connector'
CORE = NEXUS / 'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(path):
    return {p.relative_to(path).as_posix(): digest(p.read_bytes()) for p in sorted(path.rglob('*'))
        if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}


def run(command, log):
    env = {key: value for key, value in os.environ.items()
        if not key.upper().startswith(('PYTHON', 'PYTEST', 'OKTO_NEXUS', 'NEXUS_'))}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    with (ROOT / log).open('x', encoding='utf-8') as output:
        subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)


proofs, wheels = {}, [CORE]
for repo, package, version in [(NEXUS, 'okto_nexus', '0.3.3'), (CONNECTOR, 'okto_nexus_connector', '0.0.12')]:
    source = repo / 'src' / package
    before = inventory(source)
    stage = ROOT / ('build-' + package)
    stage.mkdir()
    for name in ('pyproject.toml', 'README.md', 'LICENSE', 'LICENSE.md', 'MANIFEST.in'):
        if (repo / name).is_file():
            shutil.copy2(repo / name, stage / name)
    shutil.copytree(source, stage / 'src' / package, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    assert inventory(stage / 'src' / package) == before
    run([sys.executable, '-m', 'build', '--wheel', '--no-isolation', '--outdir', str(ROOT / 'wheels'), str(stage)],
        package + '-build.log')
    wheel, = (ROOT / 'wheels').glob(package + '-' + version + '-*.whl')
    wheels.append(wheel)
    with zipfile.ZipFile(wheel) as archive:
        packaged = {n[len(package) + 1:]: digest(archive.read(n)) for n in archive.namelist()
            if n.startswith(package + '/') and not n.endswith('/')}
    assert before == inventory(source) == packaged
    proofs[package] = dict(repository=str(repo), wheel=str(wheel), wheel_sha256=digest(wheel.read_bytes()),
        version=version, pyproject_sha256=digest((repo / 'pyproject.toml').read_bytes()), files=before)
run([sys.executable, '-I', '-m', 'venv', '--system-site-packages', str(ROOT / 'venv')], 'venv-create.log')
python = ROOT / 'venv/Scripts/python.exe'
run([str(python), '-I', '-m', 'pip', '--isolated', 'install', '--ignore-installed', '--no-deps', '--no-index',
    *map(str, wheels)], 'wheel-install.log')
for package, proof in proofs.items():
    installed = ROOT / 'venv/Lib/site-packages' / package
    assert inventory(installed) == proof['files']
    proof.update(installed_package=str(installed), file_count=len(proof['files']), exact_source_build_wheel_install=True)
proof = dict(python=str(python), packages=proofs, core_wheel=str(CORE), core_sha256=digest(CORE.read_bytes()))
(ROOT / 'package-proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({k: dict(file_count=v['file_count'], wheel_sha256=v['wheel_sha256']) for k, v in proofs.items()}, indent=2))
