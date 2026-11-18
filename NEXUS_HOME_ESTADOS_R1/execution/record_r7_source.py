"""Retain the measured R6 failure and scoped R7 correction/equivalence cuts."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
stamp = datetime.now(UTC).isoformat()
perf = dict(commit='90b94ca9673c087554b7dc4a226490ef5417bd32',
    command_or_procedure='Ten exclusive paired persistent-ASGI cuts, three warmups/twenty samples per route',
    environment='Windows; immutable baseline/R6 installed prefixes and identical original mixed/OPEN seeds; no provider',
    timestamp=stamp, result='FAIL500ms: six large cases; four small cases PASS. All ten measured/ready with no drift, retry or timeout.',
    artifact_path='execution/performance-hst/persistent-r6-final/qualification.json',
    limitations='First HTTP proxy is not DOM. Mixed V2 regressed in this series; no optimization win or target waiver. Profile R6 is diagnostic only.')
source = dict(commit='9d380f75 + exact R7 source/test pins in the corrected artifact',
    command_or_procedure='Bounded coordinated source equivalence run after preserving the failed first cut',
    environment='Windows; source-only Nexus, isolated pinned dependencies; closed PIPE; no provider',
    timestamp=stamp, result='PASS87 corrected; prior cut104PASS/12FAIL retained; drift/timeout/force/remaining known processes0',
    artifact_path='execution/source-tests/r7-performance-corrected/qualification.json',
    limitations='Initial domain failure was a shadowed envelope variable, repaired before packaging; six new SQL oracle failures were trace/scope assumptions. Root identity-cache twelve cases passed in the first cut. R7 installed/browser/performance not yet run.')
for task in ledger['tasks']:
    additions = []
    if task['id'] in ('HST-027', 'HST-032'):
        additions.append(perf)
    if task['id'] in ('HST-005', 'HST-009', 'HST-010', 'HST-024', 'HST-025', 'HST-027'):
        additions.append(source)
    for entry in additions:
        task['evidence'].append(entry)
for test in ledger['tests']:
    if test['id'] in ('HST-T-J04', 'HST-T-J05'):
        test['evidence'].append(perf)
        test['status'] = 'FAIL' if test['id'] == 'HST-T-J04' else 'PASS'
ledger['execution']['performance_r6'] = dict(
    measured=10, small_pass=4, large_fail=6, threshold_p95_ms=500,
    artifact='execution/performance-hst/persistent-r6-final/qualification.json',
    diagnostic='execution/performance-hst/profile-r6-final/qualification.json',
    first_useful_dom='NOT_RUN', threshold_waived=False)
ledger['execution']['r7_source'] = dict(status='SCOPED_EQUIVALENCE_PASS87',
    changes=['Only equal-ID ties need extra canonical sort keys.',
             'Board uses the shared metadata envelope without rendering a discarded entries page.',
             'Pure group identity hash reused until its complete immutable tuple changes; no source facts cached.',
             'V2 complete authorized result-attention lookup is request-local with legacy fallbacks.'],
    schema_migration=False, core_connector_protocol_changes=False,
    previous_failure='execution/source-tests/r7-performance-focal/qualification.json',
    corrected='execution/source-tests/r7-performance-corrected/qualification.json',
    installed='PENDING_FRESH_R7', browser='PENDING', performance='PENDING_ORIGINAL_THRESHOLDS')
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
