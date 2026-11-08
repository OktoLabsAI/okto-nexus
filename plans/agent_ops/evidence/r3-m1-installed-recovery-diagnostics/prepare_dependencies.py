"""Prepare only a disposable dependency environment, never install products."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).parent
SOURCE = Path('C:/Users/jpamb/AppData/Local/Temp/m1-observation-hosts-ai03jk1l/venv/Lib/site-packages')
PREFIX = ROOT / 'venv'
SITE = PREFIX / 'Lib/site-packages'
MODULES = {'okto_nexus', 'okto_nexus_connector', 'nexus_connector_core'}
PRODUCT_DIST = re.compile(r'^(okto_nexus|okto_nexus_connector|okto_nexus_connector_core)-.*\.(dist|egg)-info$')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def excluded(path):
    return (path.name in MODULES or path.name in {name + '.py' for name in MODULES}
            or bool(PRODUCT_DIST.fullmatch(path.name)) or path.name == '__pycache__')


assert not PREFIX.exists() and not (ROOT / 'dependency-preparation.json').exists()
assert {p.name for p in SOURCE.glob('*.pth')} == {
    'distutils-precedence.pth', 'pywin32.pth', '_virtualenv.pth'}
assert not list(SOURCE.glob('*.egg-link'))
assert not list(SOURCE.glob('__editable__*'))
venv.EnvBuilder(with_pip=False, system_site_packages=False).create(PREFIX)
copied = {}
skipped = []
for entry in SOURCE.iterdir():
    if excluded(entry):
        skipped.append(entry.name)
        continue
    if entry.is_symlink():
        raise RuntimeError('dependency symlink is not permitted')
    candidates = entry.rglob('*') if entry.is_dir() else (entry,)
    for path in candidates:
        if path.is_symlink():
            raise RuntimeError('dependency symlink is not permitted')
        if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        relative = path.relative_to(SOURCE)
        target = SITE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        source_hash = sha(path.read_bytes())
        assert sha(target.read_bytes()) == source_hash
        copied[relative.as_posix()] = source_hash

environment = {}
for name in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT'):
    if name in os.environ:
        environment[name] = os.environ[name]
environment['PATH'] = os.pathsep.join([str(PREFIX / 'Scripts'), str(Path(sys.base_prefix)),
                                     str(Path(os.environ['SYSTEMROOT']) / 'System32')])
for variable, name in [('USERPROFILE', 'userprofile'), ('APPDATA', 'appdata'),
                       ('LOCALAPPDATA', 'localappdata'), ('TEMP', 'tmp'), ('TMP', 'tmp')]:
    target = ROOT / 'isolated' / name
    target.mkdir(parents=True, exist_ok=True)
    environment[variable] = str(target)
environment.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                   PIP_CONFIG_FILE=os.devnull)
environment['HOME'] = environment['USERPROFILE']
(ROOT / 'environment.json').write_text(json.dumps(environment, indent=2) + '\n', encoding='utf-8')
probe_code = '''import importlib.util, importlib.metadata as m, json, sys
from pathlib import Path
names = ('okto_nexus', 'okto_nexus_connector', 'nexus_connector_core')
specs = {n: importlib.util.find_spec(n) for n in names}
assert all(v is None for v in specs.values())
distributions = ('okto-nexus', 'okto-nexus-connector', 'okto-nexus-connector-core')
for name in distributions:
    try:
        m.distribution(name)
    except m.PackageNotFoundError:
        pass
    else:
        raise AssertionError('product distribution present')
pip_spec = importlib.util.find_spec('pip')
assert pip_spec and Path(pip_spec.origin).is_relative_to(Path(sys.prefix))
print(json.dumps({'prefix': sys.prefix, 'python': sys.executable,
    'products_find_spec': {n: None for n in names}, 'product_dist_info_absent': True,
    'pip_origin': pip_spec.origin, 'pip_version': m.version('pip'),
    'mcp_version': m.version('mcp'), 'system_site_packages': False}))
'''
argv = [str(PREFIX / 'Scripts/python.exe'), '-I', '-X', 'utf8', '-c', probe_code]
probe = subprocess.run(argv, cwd=ROOT / 'isolated', env=environment,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
(ROOT / 'dependency-probe.stdout.txt').write_bytes(probe.stdout)
(ROOT / 'dependency-probe.stderr.txt').write_bytes(probe.stderr)
assert probe.returncode == 0, 'isolated dependency probe failed; see retained logs'
result = json.loads(probe.stdout)
manifest = {'source': str(SOURCE), 'destination': str(SITE), 'files': copied}
(ROOT / 'dependency-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
report = {'status': 'DEPENDENCIES_ONLY_READY', 'products_installed': False,
          'source_modified': False, 'probe': result, 'excluded_top_level': sorted(skipped),
          'dependency_files': len(copied),
          'dependency_manifest_sha256': sha((ROOT / 'dependency-manifest.json').read_bytes()),
          'environment_sha256': sha((ROOT / 'environment.json').read_bytes()),
          'campaign_services_or_provider_used': False,
          'limits': 'Dependency copy and environment preparation are outside the future product-install-to-useful-result interval.'}
(ROOT / 'dependency-preparation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report))
