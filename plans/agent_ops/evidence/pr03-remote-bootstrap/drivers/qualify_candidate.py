"""Copy tests outside checkout; guard all three imports from installed wheels."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent / sys.argv[1]
KIND = sys.argv[2]
ROOT = BASE / ('tests-' + KIND + ('-' + sys.argv[3] if len(sys.argv) > 3 else ''))
ROOT.mkdir(exist_ok=False)
NEXUS = Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
REPO = NEXUS if KIND == 'nexus' else NEXUS.parent / 'okto-nexus-connector'
SITE = BASE / 'venv/Lib/site-packages'
for key in list(os.environ):
    if key.upper().startswith(('PYTHON', 'PYTEST', 'OKTO_NEXUS', 'NEXUS_')):
        os.environ.pop(key, None)
sys.dont_write_bytecode = True
sys.path[:] = [p for p in sys.path if p and not Path(p).resolve().is_relative_to(NEXUS.parent)]
# Dependency fallback is appended after the installed candidate, never before.
sys.path.append(str(NEXUS / '.venv/Lib/site-packages'))
home = ROOT / 'test-home'
home.mkdir()
os.environ.update(USERPROFILE=str(home), APPDATA=str(home / 'appdata'), LOCALAPPDATA=str(home / 'localappdata'),
    PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
os.chdir(ROOT)
packages = ('okto_nexus', 'okto_nexus_connector', 'nexus_connector_core')
for package in packages:
    __import__(package)
for name, version in [('okto-nexus', '0.3.3'), ('okto-nexus-connector', '0.0.12'), ('okto-nexus-connector-core', '0.0.14')]:
    assert importlib.metadata.version(name) == version
    direct = json.loads(importlib.metadata.distribution(name).read_text('direct_url.json'))
    assert direct['url'].endswith('.whl') and not direct.get('dir_info', {}).get('editable')


def guard():
    paths = {}
    for name, module in list(sys.modules.items()):
        if any(name == p or name.startswith(p + '.') for p in packages):
            raw = getattr(module, '__file__', None)
            if raw:
                assert Path(raw).resolve().is_relative_to(SITE), (name, raw)
                paths[name] = raw
    return paths


shutil.copytree(REPO / 'tests', ROOT / 'tests', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
supporting_files = {}
if KIND == 'nexus':
    relative = 'plans/contratos/http-target.schema.json'
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / relative, target)
    supporting_files[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
copied = {p.relative_to(ROOT / 'tests').as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted((ROOT / 'tests').rglob('*')) if p.is_file()}
config = ROOT / 'pytest.ini'
config.write_text('[pytest]\npythonpath =\nasyncio_mode = auto\nasyncio_default_fixture_loop_scope = function\n', encoding='utf-8')
if KIND == 'nexus':
    nodes = ['test_remote_setup_server.py', 'test_remote_setup_http.py', 'test_remote_setup_guards.py',
        'test_remote_setup_machines.py', 'test_remote_setup_epoch.py', 'test_remote_setup_capacity.py',
        'execution_r4/test_remote_terminal_setup.py', 'execution_r4/test_remote_setup_integration.py',
        'execution_r4/test_terminal_connect.py', 'execution_r4/test_remote_operator_terminal.py',
        'execution_r4/test_terminal_binding_approval.py', 'execution_r4/test_binding_operator.py',
        'execution_r4/test_remote_project_policy.py', 'execution_r4/test_connection_setup.py',
        'execution_r4/test_connection_setup_recovery.py']
else:
    nodes = json.loads((Path(__file__).parent / 'connector-nodes.json').read_text())
if len(sys.argv) > 4:
    nodes = json.loads(Path(sys.argv[4]).read_text())
assert all((ROOT / 'tests' / n.split('::')[0]).is_file() for n in nodes)
import pytest


class Guard:
    def pytest_sessionstart(self, session):
        guard()

    def pytest_runtest_setup(self, item):
        guard()

    def pytest_sessionfinish(self, session, exitstatus):
        guard()


xml = ROOT / 'installed.xml'
args = ['-q', '--tb=short', '-c', str(config), '--rootdir', str(ROOT), '-p', 'pytest_asyncio.plugin',
    '--junitxml=' + str(xml), *[str(ROOT / 'tests' / n) for n in nodes]]
code = pytest.main(args, plugins=[Guard()])
proof = dict(exit_code=int(code), python=sys.executable, cwd=str(ROOT), nodes=nodes, test_files=copied,
    supporting_files=supporting_files,
    loaded_package_modules=guard(), sys_path=sys.path, xml=str(xml), xml_sha256=hashlib.sha256(xml.read_bytes()).hexdigest(),
    dependencies={d.metadata['Name']: d.version for d in importlib.metadata.distributions() if d.metadata.get('Name')},
    counts=[dict(s.attrib) for s in ET.parse(xml).getroot().iter('testsuite')])
(ROOT / 'qualification.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({k: proof[k] for k in ('exit_code', 'cwd', 'counts')}, indent=2))
raise SystemExit(code)
