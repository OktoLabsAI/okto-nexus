"""Prepare only a disposable installed interpreter; no service commands."""
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent
WHEELS = {
    'okto_nexus': (Path('C:/Users/jpamb/AppData/Local/Temp/dx04-mcp-guide-installed-sk13m28a/candidate-v1/wheels/okto_nexus-0.3.3-py3-none-any.whl'), '9b18dc0c69673bb730198ca461f2464c8ee4ae3fdc1226f22ffcb8140783412f'),
    'okto_nexus_connector': (Path('C:/Users/jpamb/AppData/Local/Temp/remote-renewal-release-8hs8nezr/candidate-v2/wheels/okto_nexus_connector-0.0.12-py3-none-any.whl'), 'a8cf18105fa1cdca0443b6a3be08972d5576f72f3ce07e5a19dd9fc7cd59ae5a'),
    'nexus_connector_core': (Path('D:/Projetos/Techridy/okto_labs_okto_nexus/vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'), '5721e462add21d65380f070a68db07a653a498a78d4be9ea0cf949909d3cfecb'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    with (ROOT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


env = {key: value for key, value in os.environ.items()
    if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP'}}
profile = ROOT / 'isolated-profile'
profile.mkdir(exist_ok=False)
env.update(USERPROFILE=str(profile), APPDATA=str(profile / 'appdata'), LOCALAPPDATA=str(profile / 'localappdata'),
    PATH=os.pathsep.join([str(ROOT / 'venv/Scripts'), str(Path(sys.executable).parent), str(Path(os.environ['SystemRoot']) / 'System32')]),
    PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1', OKTO_NEXUS_NO_BANNER='1', OKTO_NEXUS_CONNECTOR_VAULT='file')
write('environment.json', env)


def run(command, name):
    with (ROOT / (name + '.log')).open('x', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(name + ' failed; retained log, no service operation was attempted.')


pool = ROOT / 'wheels'
pool.mkdir(exist_ok=False)
for path, expected in WHEELS.values():
    assert sha(path) == expected
    shutil.copy2(path, pool / path.name)

# Pin the currently installed compatible dependency closure without loading
# credential providers, reading their configuration, or invoking a CLI doctor.
queue = ['mcp', 'pydantic', 'fastapi', 'uvicorn', 'wsproto', 'httpx', 'websockets', 'pywin32', 'rfc8785', 'jsonschema']
versions = {}
while queue:
    name = canonicalize_name(queue.pop())
    if name in versions:
        continue
    distribution = metadata.distribution(name)
    versions[name] = distribution.version
    for item in distribution.requires or ():
        requirement = Requirement(item)
        if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
            queue.append(requirement.name)
assert versions['mcp'] == '1.30.0'
requirements = ROOT / 'requirements-pinned.txt'
with requirements.open('x', encoding='utf-8') as output:
    output.write(''.join(name + '==' + version + '\n' for name, version in sorted(versions.items())))
run([sys.executable, '-I', '-m', 'venv', str(ROOT / 'venv')], 'venv-create')
python = ROOT / 'venv/Scripts/python.exe'
run([str(python), '-I', '-m', 'pip', '--isolated', 'download', '--index-url', 'https://pypi.org/simple',
    '--no-cache-dir', '--only-binary=:all:', '--no-deps', '--dest', str(pool), '-r', str(requirements)], 'dependency-download')
run([str(python), '-I', '-m', 'pip', '--isolated', 'install', '--no-index', '--no-deps',
    *[str(path) for path in sorted(pool.glob('*.whl'))]], 'isolated-install')
run([str(python), '-I', '-m', 'pip', '--isolated', 'check'], 'pip-check')
write('environment-preparation.json', dict(status='PREPARED_ONLY_NO_CAMPAIGN', python=str(python),
    system_site_packages=False, public_dependency_index='https://pypi.org/simple',
    dependencies=versions, wheels=[dict(path=str(p), sha256=sha(p), bytes=p.stat().st_size) for p in sorted(pool.glob('*.whl'))],
    commands_executed=['venv create', 'public pinned dependency download', 'offline wheel installation', 'pip check'],
    service_operations_executed=[]))
print(json.dumps(dict(status='prepared', python=str(python), dependencies=len(versions), wheels=len(list(pool.glob('*.whl'))))))
