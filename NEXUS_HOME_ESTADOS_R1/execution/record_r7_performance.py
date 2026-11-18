"""Retain failed targets and link diagnosis/correction without a waiver."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
result = json.loads((HERE / 'performance-hst/persistent-r7-final/qualification.json').read_text())
assert result['status'] == 'FAIL' and result['candidate_counts']['read_target_fail'] == 3
assert result['candidate_counts']['measured'] == 8 and result['baseline_counts']['measured'] == 2
assert result['targets']['read_p95_ms'] == 500 and result['cleanup']['all10workers_physically_exited']
assert not result['seed_dataset_schema_payload_productive_drift']
entry = dict(commit=result['candidate_source'], timestamp=datetime.now(UTC).isoformat(),
    artifact_path='execution/performance-hst/persistent-r7-final/qualification.json',
    environment='Windows; same immutable mixed/OPEN seeds; installed baseline/R7 prefixes; exclusive persistent-ASGI window',
    command_or_procedure='Ten sequential cuts; three warmups and twenty samples per route, then a separate three-GET diagnostic',
    result='FAIL500ms: candidate5PASS/3FAIL, baseline0PASS/2FAIL; all ten measured, physical exit0 and no drift',
    limitations='First HTTP proxy is not DOM. OPEN V2 narrowly met500ms; mixed V2 overview regressed versus paired baseline. Fast path925projections proven; overlapping diagnostic costs cannot be added. Correction plan remains OPEN, no waiver.')
for task in ledger['tasks']:
    if task['id'] in ('HST-027', 'HST-032'):
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in task['evidence']):
            task['evidence'].append(entry)
for test in ledger['tests']:
    if test['id'] in ('HST-T-J04', 'HST-T-J05'):
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
            test['evidence'].append(entry)
        test['status'] = 'FAIL' if test['id'] == 'HST-T-J04' else 'PASS'
ledger['execution']['performance_r7'] = dict(
    status='FAIL_ORIGINAL_READ_TARGET', candidate_counts=result['candidate_counts'],
    baseline_counts=result['baseline_counts'], targets=result['targets'],
    matrix=entry['artifact_path'], diagnostic='execution/performance-hst/profile-r7-final/qualification.json',
    correction='execution/performance-hst/r7-correction-plan.md',
    correction_status='OPEN_NOT_IMPLEMENTED', threshold_waived=False,
    human_readiness=False, first_useful_dom='NOT_RUN')
ledger['execution']['r7_validation']['performance'] = 'FAIL500MS_CANDIDATE3_OF8; diagnosis and open correction recorded'
ledger['execution']['r7_source']['performance'] = 'FAIL_ORIGINAL500MS_TARGET; see performance_r7'
ledger['execution']['observed_scenario_reconciliation']['performance'] = 'R7_MEASURED_FAIL500MS; DOM_NOT_RUN'
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(ledger['execution']['performance_r7']))
