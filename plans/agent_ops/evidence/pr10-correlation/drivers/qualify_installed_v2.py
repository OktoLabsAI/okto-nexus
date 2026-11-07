"""Run copied PR10 contracts against the installed candidate outside checkout."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent / 'candidate-v2'
ROOT = BASE / ('tests-' + sys.argv[3])
ROOT.mkdir(exist_ok=False)
REPO = Path(sys.argv[1]).resolve()
SITE = BASE / 'venv/Lib/site-packages'
for key in list(os.environ):
    if key.upper().startswith(('PYTHON', 'PYTEST', 'OKTO_NEXUS', 'NEXUS_')):
        os.environ.pop(key, None)
sys.dont_write_bytecode = True
sys.path[:] = [p for p in sys.path if p and not Path(p).resolve().is_relative_to(REPO.parent)]
suite_home = ROOT / 'test-home'
suite_home.mkdir()
os.environ['USERPROFILE'] = str(suite_home)
os.environ['APPDATA'] = str(suite_home / 'appdata')
os.environ['LOCALAPPDATA'] = str(suite_home / 'localappdata')
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
os.chdir(ROOT)
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


for name, version in [('okto-nexus', '0.3.3'), ('okto-nexus-connector-core', '0.0.14')]:
    assert importlib.metadata.version(name) == version
    direct = json.loads(importlib.metadata.distribution(name).read_text('direct_url.json'))
    assert not direct.get('dir_info', {}).get('editable') and direct['url'].endswith('.whl')
guard()
tests = ROOT / 'tests'
tests.mkdir()
(tests / 'execution_r4').mkdir()
shutil.copytree(REPO / 'tests/fixtures/diagnostics_v1', tests / 'fixtures/diagnostics_v1')
copied = {}
for source in [*(REPO / 'tests').glob('*.py'), *(REPO / 'tests/execution_r4').glob('*.py')]:
    relative = source.relative_to(REPO / 'tests')
    target = tests / relative
    shutil.copy2(source, target)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    copied[relative.as_posix()] = dict(source=str(source), copy=str(target), sha256=digest)
config = ROOT / 'pytest.ini'
config.write_text('[pytest]\npythonpath =\n', encoding='utf-8')
suites = {
    'correlation': [
        'test_observation_correlation_domain.py',
        'test_observation_correlations_storage.py',
        'test_observation_process_birth.py',
        'test_observation_correlation_http.py',
        'test_observation_correlation_proof.py',
        'test_observation_correlation_projection.py',
        'test_observation_correlation_view.py',
        'test_observation_correlation_reads.py',
        'test_observation_settings.py',
    ],
    'regression': [
        'test_import_boundary.py', 'test_observation_service.py',
        'test_observation_http.py', 'test_observation_summary_http.py',
        'test_attention_external.py', 'test_attention_external_upgrade.py',
        'test_attention_snapshot_query.py', 'test_attention_external_query.py',
        'test_attention_engine_bounds.py', 'test_attention_api.py',
        'test_attention_stream.py', 'test_attention_storage.py',
        'execution_r4/test_external_observation_isolation.py',
    ],
    'diagnostics': ['test_diagnostic_report_contract.py',
        'test_doctor_diagnostic_format.py', 'test_project_doctor_cli.py'],
}
suites['attention-followup'] = suites['regression'] + [
    'test_observation_correlation_reads.py', 'test_attention_correlation_policy.py']
nodes = suites[sys.argv[3]]
import pytest


class Guard:
    def pytest_runtest_setup(self, item):
        guard()

    def pytest_sessionstart(self, session):
        guard()

    def pytest_sessionfinish(self, session, exitstatus):
        guard()


xml = ROOT / 'installed.xml'
exit_code = pytest.main(['-q', '-c', str(config), '--rootdir', str(ROOT),
    '--junitxml=' + str(xml), *[str(tests / node) for node in nodes]], plugins=[Guard()])
proof = dict(exit_code=int(exit_code), python=sys.executable, cwd=str(Path.cwd()),
    isolated_userprofile=str(suite_home), pytest_config=str(config), nodes=nodes,
    test_files=copied, loaded_package_modules=guard(), sys_path=sys.path, xml=str(xml),
    xml_sha256=hashlib.sha256(xml.read_bytes()).hexdigest(),
    counts=[dict(s.attrib) for s in ET.parse(xml).getroot().iter('testsuite')])
(ROOT / 'installed-qualification.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in proof.items() if key in ('exit_code', 'python', 'cwd', 'xml', 'counts')}, indent=2))
raise SystemExit(exit_code)
