"""Record the bounded R5 focal cut without inheriting installed/browser gates."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
report = json.loads((HERE / 'source-tests/r5-working-focal/qualification.json').read_text())
assert report['exit_code'] == 0 and not report['source_and_test_drift']
entry = dict(
    commit='3ea245d87635a22da2647d234338f0b728942fab + exact R5 source/test artifact pins',
    command_or_procedure='Bounded source-only focal run of six files: productive reducer, private full-key transport, actual Core ingress and legacy equivalence',
    environment='Windows; isolated source-first Nexus with pinned dependencies; inert native peer, no provider',
    timestamp=datetime.now(UTC).isoformat(),
    result='PASS90; source/test drift0; timeout/force/remaining process/listener0',
    artifact_path='execution/source-tests/r5-working-focal/qualification.json',
    limitations='Actual Core SUBMITTED/started proves Working without a RUNNING receipt. The 25-operation SQL transport fixture is synthetic read-layer evidence only. Final installed/browser/performance and full criterion reconciliation remain pending.')
for task in ledger['tasks']:
    if task['id'] in ('HST-005', 'HST-006', 'HST-007', 'HST-009', 'HST-010', 'HST-024', 'HST-025'):
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in task['evidence']):
            task['evidence'].append(entry)
ledger['execution']['r5_working_correction'].update(
    status='IMPLEMENTED_SOURCE_FOCALS_PASS90',
    source_focals='execution/source-tests/r5-working-focal/qualification.json',
    frontend='execution/frontend-r5/qualification.json',
    frontend_node='PASS404; input drift0; no browser/AT claim',
    static='execution/static-checks/r5-working.json; 31files, no increased Ruff rule counts',
    lock='uv lock --check PASS106; no lock mutation',
    final_qualification='PENDING_FRESH_R5_INSTALLED_BROWSER_PERFORMANCE')
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
