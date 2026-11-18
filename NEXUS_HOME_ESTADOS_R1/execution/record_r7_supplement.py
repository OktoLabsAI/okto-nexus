"""Add scoped supplementary evidence; preserve missing browser clauses."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ledger_path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
source = json.loads((HERE / 'supplement-r7-prepared/source-corrected/qualification.json').read_text())
installed = json.loads((HERE / 'installed-supplement-r7/qualification.json').read_text())
assert source['status'] == 'PASS_SOURCE_SCOPED' and source['counts'] == {'PASS': 7}
assert installed['counts'] == dict(PASS=7, SKIP=0, FAIL=0, NOT_RUN=0)
assert installed['junit_errors'] == 0 and installed['source_equal'] and installed['payload_equal']
assert installed['process_exit'] == 0 and not installed['known_processes_still_alive']
assert not installed['timed_out'] and not installed['force_used']
test_path = HERE.parents[1] / 'tests/home_states/test_final_boundaries_r7.py'
assert hashlib.sha256(test_path.read_bytes()).hexdigest() == '511ce2cf5fd6cea72d560d9e9475aa5cbbfe36c97c0b1f3d5d6c1750d31beb27'
ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
entry = dict(commit=installed['runtime_source_commit'] + ' + exact Root-reviewed supplementary test SHA511ce2cf',
    timestamp=datetime.now(UTC).isoformat(),
    artifact_path='execution/installed-supplement-r7/qualification.json',
    command_or_procedure='Seven exact source cases then seven actually installed cases, each finite and separately guarded',
    environment='Windows; frozen R7 prefix;1828base+1test pins;1031payload files; isolated-I-B; no provider/browser/human',
    result='PASS7SOURCE/PASS7INSTALLED; first source6PASS/1invalid-seedFAIL retained; no runtime/pin/helper drift',
    limitations='A06 query-only private sibling proof. E08/E09/E16 are historical migrated read fixtures with real HTTP/SQLite; H02/H03 API only. H07 uses SQL negative grant revocation with canonical request/denied POST, not canonical revoke lifecycle. Full browser clauses remain unverified.')
for task in ledger['tasks']:
    if task['id'] in ('HST-005', 'HST-011', 'HST-013', 'HST-025', 'HST-031', 'HST-032'):
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in task['evidence']):
            task['evidence'].append(entry)
for test in ledger['tests']:
    if test['id'] in ('HST-T-A06', 'HST-T-E08', 'HST-T-E09', 'HST-T-E16', 'HST-T-H02', 'HST-T-H03', 'HST-T-H07'):
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
            test['evidence'].append(entry)
        test['execution_notes'] = 'PARTIAL literal scenario: ' + installed['layers'][{
            'HST-T-A06': 'A06', 'HST-T-E08': 'E08_E09', 'HST-T-E09': 'E08_E09',
            'HST-T-E16': 'E16', 'HST-T-H02': 'H02_H03', 'HST-T-H03': 'H02_H03', 'HST-T-H07': 'H07',
        }[test['id']]] + '. Missing browser/native clauses remain NOT_RUN; no suite-count promotion.'
ledger['execution']['supplement_r7'] = dict(
    source='execution/supplement-r7-prepared/source-corrected/qualification.json',
    antecedent='execution/supplement-r7-prepared/source-initial/qualification.json',
    installed=entry['artifact_path'], source_pass=7, installed_pass=7,
    exact_test_sha256='511ce2cf5fd6cea72d560d9e9475aa5cbbfe36c97c0b1f3d5d6c1750d31beb27',
    runtime_reinstalled=False, prefix_mutated=False, literal_scenario_promotions=0,
    limits=installed['layers'])
ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(ledger['execution']['supplement_r7']))
