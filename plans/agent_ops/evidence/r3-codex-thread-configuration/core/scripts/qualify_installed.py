"""Offline wheel build and non-editable isolated qualification of DX43."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

root = Path('D:/Projetos/Techridy/okto-nexus-connector-core')
out = Path(__file__).parent
build_source = out / 'build-source'
wheel_dir = out / 'wheel'
venv = out / 'venv'
isolated = out / 'isolated'
sha = lambda b: hashlib.sha256(b).hexdigest()


def run(name, argv, cwd=out):
    log = out / (name + '.log')
    assert not log.exists()
    with log.open('wb') as stream:
        result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    (out / (name + '.json')).write_text(json.dumps({
        'argv': [str(v) for v in argv], 'cwd': str(cwd),
        'returncode': result.returncode, 'log_sha256': sha(log.read_bytes()),
    }, indent=2) + '\n', encoding='utf-8')
    if result.returncode:
        raise RuntimeError(name + ' failed; retained log')


assert not build_source.exists() and not isolated.exists() and not venv.exists()
build_source.mkdir()
for name in ('pyproject.toml', 'README.md', 'LICENSE'):
    shutil.copy2(root / name, build_source / name)
shutil.copytree(root / 'src', build_source / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.egg-info'))
run('build', [sys.executable, '-X', 'utf8', '-m', 'build', '--wheel', '--no-isolation',
              '--outdir', wheel_dir, build_source])
wheels = list(wheel_dir.glob('*.whl'))
assert len(wheels) == 1
wheel = wheels[0]
run('venv', [sys.executable, '-m', 'venv', '--system-site-packages', venv])
python = venv / 'Scripts/python.exe'
run('install', [python, '-I', '-m', 'pip', 'install', '--no-index', '--no-deps',
                '--no-compile', wheel])
shutil.copytree(root / 'tests', isolated / 'tests', ignore=shutil.ignore_patterns('__pycache__'))
(isolated / 'pytest.ini').write_text('[pytest]\nasyncio_default_fixture_loop_scope = function\n', encoding='utf-8')
package_root = 'nexus_connector_core'
source = {p.relative_to(root / 'src').as_posix(): sha(p.read_bytes())
          for p in (root / 'src' / package_root).rglob('*')
          if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
with zipfile.ZipFile(wheel) as archive:
    payload = {name: sha(archive.read(name)) for name in archive.namelist()
               if name.startswith(package_root + '/') and not name.endswith('/')}
installed = {p.relative_to(venv / 'Lib/site-packages').as_posix(): sha(p.read_bytes())
             for p in (venv / 'Lib/site-packages' / package_root).rglob('*')
             if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
assert source == payload == installed
proof = {'schema': 1, 'wheel': str(wheel), 'wheel_sha256': sha(wheel.read_bytes()),
         'payload_count': len(source), 'source_wheel_installed_equal': True,
         'source': str(root), 'installed': str(venv / 'Lib/site-packages' / package_root),
         'files': source}
(out / 'package-proof.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in proof.items() if k != 'files'}), flush=True)
run('installed-run', [python, '-I', '-X', 'utf8', out / 'run_installed.py'], cwd=isolated)
