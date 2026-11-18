"""Reconcile exact observed layers; retain failures, partials and external gates."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
review_path = HERE / 'scenario-final-review-r5-prepared.json'
review = json.loads(review_path.read_text())
stamp = datetime.now(UTC).isoformat()


def evidence(result, artifact, command, limits, commit='90b94ca9673c087554b7dc4a226490ef5417bd32'):
    return dict(commit=commit, command_or_procedure=command,
        environment='Windows; isolated source/installed/browser fixtures; no real provider or human',
        timestamp=stamp, result=result, artifact_path=artifact, limitations=limits)


rows = {row['id']: row for row in review['scenarios']}
for test in ledger['tests']:
    row = rows[test['id']]
    entry = evidence('Audit: ' + row['assessment'], 'execution/scenario-final-review-r5-prepared.json',
        'Review literal Given/When/Then and required layer against exact executed XML/Node/browser assertions',
        row['rationale'] + ' Historical review; later observed cuts below take precedence.',
        'R3/R4/R5 evidence cuts and exact hashes identified by the review')
    if not any(old.get('artifact_path') == entry['artifact_path'] for old in test['evidence']):
        test['evidence'].append(entry)
    if row['assessment'] == 'PASS' and test['status'] not in ('FAIL', 'BLOCKED'):
        test['status'] = 'PASS'
    if test['status'] == 'NOT_RUN':
        test['execution_notes'] = ('PARTIAL assertion coverage; full literal criterion not verified. ' if row['assessment'] == 'PARTIAL' else '') + row['rationale']

updates = [
    (('HST-T-C03', 'HST-T-C04', 'HST-T-D09'), evidence(
        'PASS scoped canonical Core/SQLite and browser transition chain',
        'execution/browser-hst/cuts/r5-working-draft-terminal/qualification.json',
        'Actual inert-peer started/progress, blocking question and independent terminal; one explicit answer and later exact result',
        'R5 execution, backend bytes identical in R6. No real adapter/provider or causal application acknowledgement; D08 remains blocked.',
        '8df456d1079313cc38e3cfe674ae4cc2b04fb64b')),
    (('HST-T-E10', 'HST-T-E12', 'HST-T-E14', 'HST-T-E15'), evidence(
        'PASS scoped read contracts; canonical rejection1 plus historical read variants5',
        'execution/installed-supplement-r6/qualification.json',
        'Post-build R6 installed supplementary tests; ASGI/SQLite Results, exact targets/history and unchanged productive rows',
        'Six Results cases: one canonical coordination tool rejection; five synthetic migrated read fixtures. Not native producer/physical runtime proof. Current Node presentation evidence is separate.')),
    (('HST-T-F06',), evidence(
        'PASS draft node/selection/focus retained through real delayed info; earlier failure retained',
        'execution/browser-hst/cuts/r6-info-draft-focus/qualification.json',
        'Info12s while editing; close restores focus, board blur adopts version2; zero browser POST',
        'Stable two-poll/explicit-answer branch separately passed in R5. No AT/human claim.')),
    (('HST-T-G07', 'HST-T-G08'), evidence(
        'PASS scoped compact Home and explicit Chat/Ask choices; unrelated coordinate oracle limitation retained',
        'execution/browser-hst/cuts/r6-mobile-intents-derivative/qualification.json',
        'Actual packaged UI choices, aria-pressed, project, submit labels and menu-closed captures; current Node404 and canonical operator/API supplementary cases',
        'Browser choice checks are zero POST; operator message/handoff identity is verified separately by two actual R6 API cases. Not native zoom/AT or full I05 qualification.')),
    (('HST-T-K01', 'HST-T-K04'), evidence(
        'PASS scoped contract and installed artifact', 'execution/package-hst-r6/qualification.json',
        'New wheel/sdist/install/smoke/audit/live and real packaged browser; V1/V2 contract/revision/validator tests plus current Node404',
        '251 backend tests ran on R5 with exact R6 backend equivalence; eleven additional tests actually ran on R6. No old-client browser, all-OS, native campaign or default activation claim.')),
]
for test_ids, entry in updates:
    for test in ledger['tests']:
        if test['id'] in test_ids:
            test['status'] = 'PASS'
            if not any(old.get('artifact_path') == entry['artifact_path'] and old.get('result') == entry['result'] for old in test['evidence']):
                test['evidence'].append(entry)
            test['execution_notes'] = entry['limitations']

contract = evidence('BLOCKED positive producer premise; conservative fallback implemented',
    'execution/contract-blockers-r6-review.json',
    'Trace current adapter/Server/Core producers and read exact contract limitations',
    'C07 independent queue proof absent; C08 same request immutable; D02 permission-specific block proof not supplied; D08 causal application/resume ACK absent. No Core/protocol changes or invented proof.')
for test in ledger['tests']:
    if test['id'] in ('HST-T-C07', 'HST-T-C08', 'HST-T-D02', 'HST-T-D08'):
        test['status'] = 'BLOCKED'
        if not any(old.get('artifact_path') == contract['artifact_path'] for old in test['evidence']):
            test['evidence'].append(contract)
        test['execution_notes'] = contract['limitations']
    if test['id'] in ('HST-T-E08', 'HST-T-E09'):
        test['evidence'].append(evidence('PARTIAL actual failed/cancelled browser labels and no generic retry',
            'execution/browser-hst/cuts/r5-failed-cancelled/qualification.json',
            'Canonical inert protocol failed/cancelled terminals, retained harness and specific delivery labels',
            'Partial-output rendering was not asserted; full literal scenario remains NOT_RUN, not PASS.'))
    if test['id'] == 'HST-T-H04':
        test['evidence'].append(evidence('PARTIAL API3 original-recipient authorization; wrong actors403',
            'execution/installed-supplement-r6/qualification.json',
            'Three existing native-decision cases executed on the immutable R6 prefix',
            'Browser adversarial other-recipient interaction remains unexecuted.'))

aggregate = evidence('PARTIAL qualification; implementation and observed layers recorded without default approval',
    'execution/browser-hst/r5-r6-final-report.md',
    'Reconcile source90/251, installed R5 251, R6 supplement11, current frontend404 and individually scoped browser cuts',
    'Performance final window pending; native contracts, real providers, AT, human and prior broad gates remain explicit. No blanket PASS from a suite count.')
for requirement in ledger['requirements']:
    requirement['status'] = 'PARTIAL'
    requirement.setdefault('evidence', []).append(aggregate)
    requirement['execution_notes'] = 'Implemented/partially qualified; inspect linked tasks and literal scenario evidence. No complete/default gate inferred.'
for task in ledger['tasks']:
    if task['id'] == 'HST-030':
        task['status'] = 'IMPLEMENTED'
        task['evidence'].append(evidence('PASS documentation updated; no release/default claim',
            'execution/package-cuts-reading-note.md',
            'Update public Home semantics, changelog, rollback and qualification reading notes',
            'Human acceptance, all-adapter qualification and performance targets remain separate.'))
    if task['id'] == 'HST-032':
        task['status'] = 'IN_PROGRESS'
        task['evidence'].append(aggregate)
ledger['execution']['observed_scenario_reconciliation'] = dict(
    procedure='execution/reconcile_observed_scenarios_r6.py',
    base_review='execution/scenario-final-review-r5-prepared.json',
    producer_contracts='execution/contract-blockers-r6-review.json',
    results_security_gaps='execution/results-security-gap-review-r6.json',
    supplemental_r6='execution/installed-supplement-r6/qualification.json',
    human='DEFERRED; no participant action requested', default_rollout=False,
    performance='PENDING_FINAL_EXCLUSIVE_WINDOW')
ledger['execution']['r6_ui'].update(status='IMPLEMENTED_AND_SCOPED_BROWSER_VERIFIED',
    installed='PASS build/install/live; exact backend equivalence with R5',
    browser='Info9PASS; Working/intents10PASS; derivative choices9PASS with coordinate-oracle limitation; auth/pause5 positives plus v1-selector limitation',
    supplemental_installed='11PASS actually executed on R6; no mutation of the wheel/prefix')
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
