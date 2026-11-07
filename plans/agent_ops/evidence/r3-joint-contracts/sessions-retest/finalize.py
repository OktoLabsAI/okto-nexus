"""Close the focused retest and record original-checkout stability."""
from pathlib import Path
import hashlib
import importlib.util
import json
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent
source = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
spec = importlib.util.spec_from_file_location('original_runner', source / 'tools/ci_installed.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
before = json.loads((root / 'original-checkout-before.json').read_text(encoding='utf-8'))
after = runner.input_hashes()
changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
assert not changed, changed
stamp = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
(root / 'input-stability.json').write_text(json.dumps({
    'original_checkout': str(source), 'input_count_before': len(before), 'input_count_after': len(after),
    'changed_inputs': changed, 'before_sha256': stamp(before), 'after_sha256': stamp(after),
    'scope': 'Original CI runner input_hashes scope; excludes evidence and caches.',
    'original_helper_sha256': hashlib.sha256((source / 'tests/execution_r4/test_remote_connection.py').read_bytes()).hexdigest(),
    'adapted_temp_helper_sha256': hashlib.sha256((root / 'project/tests/execution_r4/test_remote_connection.py').read_bytes()).hexdigest(),
}, indent=2) + '\n', encoding='utf-8')
initial = Path('C:/Users/jpamb/AppData/Local/Temp/r3-rg04-installed-9h8px6xo')
seen = {}
records = []
for location in (initial, root):
    xml = location / 'reports/tests.xml'
    for case in ET.parse(xml).getroot().iter('testcase'):
        identity = case.get('classname', '') + '::' + case.get('name', '')
        status = next((tag for tag in ('failure', 'error', 'skipped') if case.find(tag) is not None), 'passed')
        seen[identity] = status
        records.append({'identity': identity, 'status': status, 'report': str(xml)})
assert len(seen) == 17 and set(seen.values()) == {'passed'}
campaign = json.loads((root / 'reports/campaign.json').read_text(encoding='utf-8'))
assert campaign['status'] == 'PASS' and campaign['changed_inputs'] == []
(root / 'qualification.json').write_text(json.dumps({
    'scenario': 'RG-04', 'unique_qualified_test_identities': len(seen), 'historical_executions': len(records),
    'historical_passes': sum(record['status'] == 'passed' for record in records),
    'historical_failures': sum(record['status'] == 'failure' for record in records),
    'final_by_identity': seen, 'records': records,
    'initial_failure': 'The manually assembled DaemonApp fixture did not initialize service_generation before canonical shutdown. The initial report is immutable.',
    'affected_retest': 'One existing remote one-shot case only, using the shared proposed test-helper adaptation in a Temp mirror. No production or installed package bytes changed.',
    'checkout_patch_applied': False,
    'global_plan_or_ledger_status_changed': False,
    'scope_limit': 'Synthetic native peers and provider candidates; real installed Nexus/Core/Connector, SQLite, MCP/HTTP and selected remote WebSocket path. This is not real-provider or native-service qualification.',
}, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'changed_original_inputs': changed, 'original_input_count': len(before),
                  'unique_qualified': len(seen), 'historical_executions': len(records)}))
