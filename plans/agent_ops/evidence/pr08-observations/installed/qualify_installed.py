"""Run copied tests against only the locally installed Nexus/Core wheels."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent / 'qualified'
REPO = Path(sys.argv[1]).resolve()
SITE = ROOT / 'venv/Lib/site-packages'
for key in list(os.environ):
    if key.upper().startswith(('PYTHON', 'PYTEST', 'OKTO_NEXUS', 'NEXUS_')):
        os.environ.pop(key, None)
sys.dont_write_bytecode = True
sys.path[:] = [p for p in sys.path if p and not Path(p).resolve().is_relative_to(REPO.parent)]
os.chdir(ROOT)
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
names = ['conftest.py', 'fake_clock.py', 'test_import_boundary.py', 'test_migrations.py',
         'test_observations_storage.py', 'test_observations_domain.py',
         'test_observation_service.py', 'test_observation_http.py']
copied = {}
for name in names:
    original, target = REPO / 'tests' / name, tests / name
    shutil.copy2(original, target)
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    copied[name] = {'source': str(original), 'copy': str(target), 'sha256': digest}
config = ROOT / 'pytest.ini'
config.write_text('[pytest]\npythonpath =\n', encoding='utf-8')
nodes = [
    'test_import_boundary.py',
    'test_observations_domain.py::test_parse_returns_immutable_detached_canonical_report_without_authority_fields',
    'test_observations_domain.py::test_canonical_hash_normalizes_timezone_default_nulls_and_key_order',
    'test_observations_domain.py::test_observation_tokens_have_exclusive_family_and_hash_only_representation',
    'test_migrations.py::test_unknown_ledger_version_fails_closed_before_applying_anything',
    'test_observations_storage.py::test_upgrade_163_additive_no_seed_authority_and_repository_wiring',
    'test_observation_http.py::test_wired_management_publish_and_passive_historical_reads',
    'test_observation_service.py::test_publish_changes_no_coordination_presence_or_capacity',
    'test_observation_service.py::test_replay_after_ttl_and_policy_change_returns_exact_receipt',
    'test_observation_service.py::test_atomic_batch_failure_rolls_back_head_quota_and_event',
    'test_observation_service.py::test_event_failure_rolls_back_head_and_quota',
    'test_observation_http.py::test_bounded_strict_http_errors_never_echo_input[canonical-oversize]',
]
import pytest


class Guard:
    def pytest_sessionstart(self, session):
        guard()

    def pytest_sessionfinish(self, session, exitstatus):
        guard()


xml = ROOT / 'pr08-observation-installed-initial.xml'
exit_code = pytest.main(['-q', '-c', str(config), '--rootdir', str(ROOT),
    '--junitxml=' + str(xml), *[str(tests / node) for node in nodes]], plugins=[Guard()])
proof = {'revision': 1, 'exit_code': int(exit_code), 'python': sys.executable,
         'cwd': str(Path.cwd()), 'pytest_config': str(config), 'nodes': nodes,
         'test_files': copied, 'loaded_package_modules': guard(),
         'sys_path': sys.path, 'xml': str(xml),
         'xml_sha256': hashlib.sha256(xml.read_bytes()).hexdigest()}
proof['counts'] = [dict(s.attrib) for s in ET.parse(xml).getroot().iter('testsuite')]
(ROOT / 'installed-qualification.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in proof.items() if k in ('exit_code', 'python', 'cwd', 'xml', 'counts')}, indent=2))
raise SystemExit(exit_code)
