"""Record fresh R8 packaging separately from predecessor backend test reuse."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE / 'package-hst-r8'
SOURCE = '6eaa325ea3ddf1dec1b03475b27f373211c81e53'
WHEEL = 'fc2afcccdf55236db21071a132a353a13cf1c56399767ea5223a69e50162902e'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


manifest = read(PACKAGE / 'curation-manifest.json')
assert len(manifest) == 40
for name, expected in manifest.items():
    assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected, name
ready = read(PACKAGE / 'READY.json')
qualification = read(PACKAGE / 'qualification.json')
live = read(PACKAGE / 'live-qualification.json')
equivalence = read(PACKAGE / 'runtime-equivalence-vs-r7.json')
assert ready['source_commit'] == SOURCE and ready['wheel_sha256'] == WHEEL
assert qualification['status'] == 'PASS_BUILD_INSTALL_SMOKE'
assert live['status'] == 'PASS' and live['cleanup_verified'] and live['provider_calls'] == 0
assert live['source_drift'] == [] and live['payload_drift'] is False
assert live['process']['remaining_known_processes'] == live['process']['remaining_listeners'] == []
assert equivalence['total_runtime_nonstatic_files'] == 1024
assert equivalence['python_version_equal'] and equivalence['dependency_versions_equal']
assert equivalence['pytest_executed_on_r8'] is False

path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = read(path)
entry = dict(commit=SOURCE, timestamp=datetime.now(UTC).isoformat(),
    artifact_path='execution/package-hst-r8/qualification.json',
    environment='New isolated R8 prefix; pinned Core0.0.14/Connector0.0.13; original installation untouched',
    command_or_procedure='Build/install/base Core/local lite/Connector/pip check/Twine/audit/CLI plus actual HTTP-MCP smoke',
    result='PASS fresh R8 package; 1829 source pins/1031 payload files unchanged; 54 MCP tools/two fixture identities; normal exit and physical absence',
    limitations='No real harness/provider or new pytest run. R7 installed 326+7 tests are reusable only for 1024 byte-identical nonstatic backend files; frontend requires R8 browser evidence.')
for task in ledger['tasks']:
    if task['id'] in ('HST-028', 'HST-031', 'HST-032'):
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in task['evidence']):
            task['evidence'].append(entry)
ledger['execution']['r8_package'] = dict(source=SOURCE, wheel_sha256=WHEEL,
    ready='execution/package-hst-r8/READY.json', qualification=entry['artifact_path'],
    live='execution/package-hst-r8/live-qualification.json',
    equivalence='execution/package-hst-r8/runtime-equivalence-vs-r7.json',
    runtime_equal_files=1024, pytest_r8_executed=False,
    predecessor_installed_backend_tests='326+7, actually executed on immutable R7 prefix',
    frontend_reuse=False, default_approved=False, provider_calls=0)
ledger['execution']['r8_menu_accessibility']['installed'] = 'PASS_FRESH_R8_PACKAGE; browser still pending'
ledger['execution']['local_usability_candidate'].update(runtime_source=SOURCE, wheel_sha256=WHEEL,
    state='ADDITIONAL_FUNCTIONAL_QUALIFICATION_IN_PROGRESS; fresh R8 package ready, browser pending')
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': 'RECORDED', 'manifest_files': len(manifest), 'scenario_status_changes': 0}))
