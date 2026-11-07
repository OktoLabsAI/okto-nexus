"""Run copied tests against only the locally installed Nexus/Core wheels."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent / 'qualified-v2'
REPO = Path(sys.argv[1]).resolve()
SITE = ROOT / 'venv/Lib/site-packages'
for key in list(os.environ):
    if key.upper().startswith(('PYTHON', 'PYTEST', 'OKTO_NEXUS', 'NEXUS_')):
        os.environ.pop(key, None)
sys.dont_write_bytecode = True
sys.path[:] = [p for p in sys.path if p and not Path(p).resolve().is_relative_to(REPO.parent)]
home = ROOT / 'test-home'
home.mkdir()
for key in ('HOME', 'USERPROFILE'):
    os.environ[key] = str(home)
os.environ['APPDATA'] = str(home / 'appdata')
os.environ['LOCALAPPDATA'] = str(home / 'localappdata')
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
os.chdir(ROOT)
# Shared dependencies only; Nexus and Core remain pinned to the local wheel.
if len(sys.argv) > 2:
    sys.path.append(str(Path(sys.argv[2]).resolve()))
import okto_nexus
import nexus_connector_core


def guard():
    paths = {}
    for name, module in list(sys.modules.items()):
        if name == 'okto_nexus' or name.startswith('okto_nexus.') or name == 'nexus_connector_core' or name.startswith('nexus_connector_core.'):
            raw = getattr(module, '__file__', None)
            if raw:
                path = Path(raw).resolve()
                assert path.is_relative_to(SITE), (name, str(path))
                paths[name] = str(path)
    assert not any(Path(p).resolve().is_relative_to(REPO) for p in sys.path if p)
    return paths


assert importlib.metadata.version('okto-nexus') == '0.3.3'
assert importlib.metadata.version('okto-nexus-connector-core') == '0.0.14'
for name in ('okto-nexus', 'okto-nexus-connector-core'):
    direct = json.loads(importlib.metadata.distribution(name).read_text('direct_url.json'))
    assert not direct.get('dir_info', {}).get('editable')
    assert direct['url'].endswith('.whl')
guard()
tests = ROOT / 'tests'
tests.mkdir()
names = ['conftest.py', 'fake_clock.py', 'test_import_boundary.py',
         'test_herdr_observer.py', 'test_observation_client.py',
         'test_herdr_observations.py', 'test_herdr_windows_identity.py',
         'test_herdr_transport.py', 'test_observation_journal.py', 'test_observe_cli.py']
copied = {}
for name in names:
    original, target = REPO / 'tests' / name, tests / name
    shutil.copy2(original, target)
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    copied[name] = {'source': str(original), 'copy': str(target), 'sha256': digest}
docs = ROOT / 'docs'
docs.mkdir()
example = REPO / 'docs/observation-client-example.py'
shutil.copy2(example, docs / example.name)
copied['docs/' + example.name] = {'source': str(example), 'copy': str(docs / example.name),
    'sha256': hashlib.sha256(example.read_bytes()).hexdigest()}
config = ROOT / 'pytest.ini'
config.write_text('[pytest]\npythonpath =\n', encoding='utf-8')
nodes = [name for name in names if name.startswith('test_')]
import pytest


class Guard:
    def pytest_runtest_setup(self, item):
        guard()

    def pytest_sessionstart(self, session):
        guard()

    def pytest_sessionfinish(self, session, exitstatus):
        guard()


xml = ROOT / 'pr09-observation-installed-v2-initial.xml'
exit_code = pytest.main(['-q', '-c', str(config), '--rootdir', str(ROOT),
    '--junitxml=' + str(xml), *[str(tests / node) for node in nodes]], plugins=[Guard()])
proof = {'revision': 1, 'exit_code': int(exit_code), 'python': sys.executable,
         'cwd': str(Path.cwd()), 'isolated_home': str(home), 'pytest_config': str(config), 'nodes': nodes,
         'test_files': copied, 'loaded_package_modules': guard(),
         'sys_path': sys.path, 'xml': str(xml),
         'xml_sha256': hashlib.sha256(xml.read_bytes()).hexdigest()}
proof['counts'] = [dict(s.attrib) for s in ET.parse(xml).getroot().iter('testsuite')]
(ROOT / 'installed-qualification.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in proof.items() if k in ('exit_code', 'python', 'cwd', 'xml', 'counts')}, indent=2))
raise SystemExit(exit_code)
