"""Review completed predicate captures; do not rewrite wrapper/oracle failures."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
browser = HERE / 'browser-hst'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


history = [read(browser / 'cuts/r7-history-small' / name) for name in (
    'history-open-result.json', 'reload-verify-result.json', 'back-verify-result.json',
    'forward-verify-result.json', 'invalid-result.json')]
assert sum(len(row['checks']) for row in history) == 9
assert all(check['ok'] for row in history for check in row['checks'])
dirty = read(browser / 'cuts/r7-dirty-small/dirty-result.json')
auth = read(browser / 'cuts/r7-dirty-small/auth-result.json')
offline = read(browser / 'remaining-cuts/r7-dirty-small/offline-ui-denial.json')
assert len(dirty['checks']) == 6 and all(row['ok'] for row in dirty['checks'])
assert all(row['ok'] for row in auth['checks'][:2])
assert auth['checks'][2]['id'] == 'canonical-ui-denial-observed' and not auth['checks'][2]['ok']
assert offline['browser_post_count'] == 0
assert len(offline['actual_denied_ui_reads']) == 2
assert all(row['status'] == 401 and '/runtime/sessions/' in row['path'] for row in offline['actual_denied_ui_reads'])
for cut in ('r7-history-small', 'r7-dirty-small'):
    cleanup = read(browser / 'cuts' / cut / 'qualification.json')['cleanup']
    assert cleanup['supervisor']['exit_code'] == 0 and not cleanup['supervisor']['signals']
    assert not cleanup['own_root_processes'] and not cleanup['listener_pids']
ledger = read(LEDGER)
stamp = datetime.now(UTC).isoformat()


def evidence(result, artifact, procedure, limits):
    return dict(commit='01b0de385398950ac4547aa8a5dcbc29473c12cb', timestamp=stamp,
        result=result, artifact_path='execution/' + artifact,
        command_or_procedure=procedure,
        environment='Frozen R7 installed runtime; own Windows Chrome profiles and canonical inert-peer setup; no provider/human',
        limitations=limits)


observed = evidence('PASS literal F14/I06 supported-browser predicates:9history positives,8draft/auth positives plus offline actual UI401 proof',
    'browser-hst/remaining-report.md',
    'Review real reload/Back/Forward, exact retained target/full preflight scope, invalid-reference denial, Escape/discard/project/no-copy and canonical logout',
    'History wrapper status-label mismatch and late auth observer FAIL remain unchanged. Offline ASGI proof supplies the already-observed native session/events401, not an invented page event. UA modal blocks direct external Project interaction; explicit discard precedes real switch. No AT, native adapter or whole-plan claim.')
for test in ledger['tests']:
    if test['id'] in ('HST-T-F14', 'HST-T-I06'):
        test['status'] = 'PASS'
        if not any(row.get('artifact_path') == observed['artifact_path'] for row in test['evidence']):
            test['evidence'].append(observed)
        test['execution_notes'] = observed['limitations']
for task in ledger['tasks']:
    if task['id'] in ('HST-004', 'HST-019', 'HST-020', 'HST-021', 'HST-022', 'HST-025', 'HST-026', 'HST-028', 'HST-032'):
        if not any(row.get('artifact_path') == observed['artifact_path'] for row in task['evidence']):
            task['evidence'].append(observed)
honesty = evidence('PASS scoped reporting integrity; no whole-plan/default/human acceptance inferred',
    'release-report.md', 'Review actual executed/nonexecuted layers, immutable failures, user shared-machine guidance and prior gates',
    'Remaining literal scenarios stay NOT_RUN/BLOCKED. Native contracts, real providers/topology, AT/native zoom and prior UI/QuickConnect/broad gates are retained. Controlled production performance is unqualified; local timings are diagnostic per user.')
assert not ledger['execution']['default_rollout_approved']
assert ledger['execution']['real_provider_campaign'] == 'NOT_AUTHORIZED'
assert len(ledger['execution']['retained_gates']) >= 3
for test in ledger['tests']:
    if test['id'] == 'HST-T-K06':
        test['status'] = 'PASS'
        if not any(row.get('artifact_path') == honesty['artifact_path'] for row in test['evidence']):
            test['evidence'].append(honesty)
        test['execution_notes'] = honesty['limitations']
ledger['execution']['remaining_functional_r7'] = dict(
    report='execution/browser-hst/remaining-report.md',
    literal_observed_pass=['HST-T-F14', 'HST-T-I06'],
    wrapper_oracle_failures_preserved=True, physical_cleanup='normal0/no signals/own processes and listeners absent',
    real_provider=False, AT=False, human=False)
ledger['execution']['local_usability_candidate'] = dict(
    state='SUPPORTED_LOCAL_FLOWS_REVIEWED; participant not yet invited',
    runtime_source='01b0de385398950ac4547aa8a5dcbc29473c12cb',
    wheel_sha256='18c948b49844c7c551360732970fdc2ba91cba50075b73c1a7472571775d7681',
    supported_scope=['Working/Idle/unknown and partial/full blocking',
        'Exact request/session/result context; same receipt after response loss and stale second screen',
        'Paging409, reload/history, dirty discard/project isolation and logout'],
    performance='Diagnostic/non-blocking on shared machine per user',
    whole_plan_complete=False, default_approved=False,
    remaining_qualification='Inspect literal NOT_RUN/BLOCKED rows and remaining-qualification-review-r7.md',
    provisioning='No short-lived human fixture until participant confirms availability')
LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(ledger['execution']['remaining_functional_r7']))
