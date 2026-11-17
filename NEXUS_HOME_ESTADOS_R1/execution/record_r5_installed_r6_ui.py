"""Record R5 installed evidence and the unqualified R6 browser correction."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
installed = json.loads((HERE / 'package-hst-r5/installed-qualification.json').read_text())
assert installed['counts'] == dict(PASS=251, SKIP=0, FAIL=0, NOT_RUN=0)
stamp = datetime.now(UTC).isoformat()


def evidence(commit, command, result, artifact, limits):
    return dict(commit=commit, command_or_procedure=command,
        environment='Windows; owned temporary homes/prefixes; no provider or human participant',
        timestamp=stamp, result=result, artifact_path=artifact, limitations=limits)


backend = evidence('8df456d1079313cc38e3cfe674ae4cc2b04fb64b',
    'Fresh R5 installed Home/SQLite/HTTP selection, one shard, with copied tests/helpers and origin/payload/source guards',
    'PASS251; SKIP/FAIL/ERROR/NOT_RUN0; drift/timeout/force/remaining processes0',
    'execution/package-hst-r5/installed-qualification.json',
    'No real-provider/AT/human/performance acceptance. Source-first broader selection separately PASS251. R3 Quick Connect remains historical, not repeated here.')
ui = evidence('2cb24076 + exact Original frontend/compiler pins in artifact',
    'Current Original npm test and TypeScript/Vite build after isolated UI review and cherry-pick',
    'PASS404 Node and production build; no input drift; generated index-CefKJTtn.js',
    'execution/frontend-r6-original/qualification.json',
    'G08 intention labels and delayed-info form-preservation changes are implemented, not browser verified. Worktree raw byte equivalence was not claimed: EOL drift caused a fresh Original test/build. New installed R6 and browser checks pending.')
info_failure = evidence('8df456d1079313cc38e3cfe674ae4cc2b04fb64b',
    'Real Chromium with canonical native question and actual /info response delayed twelve seconds',
    'FAIL: selected option lost, old form node disconnected and focus moved when presentation1 upgraded to2; zero POST',
    'execution/browser-hst/cuts/r5-info-upgrade-observables/qualification.json',
    'R5 antecedent retained. Normal physical exit0, but runtime-close helper reached its thirty-second guard before lifespan drain; not a timeout-free cleanup claim. R6 reader/UI correction awaits its own browser proof.')
for task in ledger['tasks']:
    additions = []
    if task['id'] in ('HST-003', 'HST-005', 'HST-006', 'HST-007', 'HST-009', 'HST-010', 'HST-024', 'HST-025', 'HST-031'):
        additions.append(backend)
    if task['id'] in ('HST-014', 'HST-015', 'HST-016', 'HST-017', 'HST-018', 'HST-019', 'HST-020', 'HST-021', 'HST-022', 'HST-023', 'HST-028'):
        additions.append(ui)
    if task['id'] in ('HST-004', 'HST-018', 'HST-021', 'HST-028'):
        additions.append(info_failure)
    for entry in additions:
        if not any(old.get('artifact_path') == entry['artifact_path'] for old in task['evidence']):
            task['evidence'].append(entry)
for test in ledger['tests']:
    if test['id'] in ('HST-T-B01', 'HST-T-B02'):
        test['status'] = 'PASS'
        test['evidence'].append(backend)
        test['execution_notes'] = ('Scoped unit/canonical Core/SQLite proof, including actual SUBMITTED+started Working and terminal/live Idle with separate Results. '
                                   'No provider process claim; earlier failed cuts remain in evidence.')
    if test['id'] == 'HST-T-F06':
        test['status'] = 'FAIL'
        test['evidence'].append(info_failure)
        test['execution_notes'] = 'Normal stable polling preserved draft in R5; the separately delayed-info capability change exposed a real remount. R6 fix awaiting browser.'
ledger['execution']['r5_working_correction'].update(
    status='IMPLEMENTED_AND_SCOPED_SOURCE_INSTALLED_VERIFIED',
    source_regression='PASS251; execution/source-tests/r5-home/qualification.json',
    installed='PASS251; execution/package-hst-r5/installed-qualification.json',
    live='PASS54tools/twoidentities; canonical stop0 and physical exit0',
    final_qualification='R6_UI_AND_PERFORMANCE_PENDING; R5 info-remount antecedent retained')
ledger['execution']['r6_ui'] = dict(
    status='IMPLEMENTED_NOT_BROWSER_VERIFIED', frontend='execution/frontend-r6-original/qualification.json',
    changes=['Intention labels preserve canonical kinds/IDs/operator/permissions.',
             'Defer presentation-only capability switches while context/pause/keyboard focus or focus restoration is active.',
             'Identity/project/authorization clearing remains independent and immediate.'],
    package='execution/package-hst-r6', installed='PENDING', browser='PENDING',
    performance='PENDING_FINAL_EXCLUSIVE_WINDOW', human='DEFERRED')
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
