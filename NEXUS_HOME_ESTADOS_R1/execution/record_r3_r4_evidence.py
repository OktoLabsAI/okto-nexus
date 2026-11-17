"""Append immutable package/browser cuts without promoting the final gate."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
stamp = datetime.now(UTC).isoformat()


def evidence(commit, procedure, result, artifact, limitations):
    return dict(commit=commit, command_or_procedure=procedure,
                environment='Windows; isolated installed wheels; no provider or human participant',
                timestamp=stamp, result=result, artifact_path=artifact,
                limitations=limitations)


cuts = [
    (('HST-025', 'HST-031'), evidence(
        '042585b4c622948261a50b550fec3616e2743e45',
        'Installed-only copied-test qualification with origin, payload, source and helper guards',
        'PASS746, SKIP8; timeout/force/drift/remaining processes0',
        'execution/package-hst-r3/installed-qualification.json',
        'R3 only. Eight literal POSIX/non-TTY skips; collection and launcher antecedents retained. '
        'Not browser, accessibility, native console, real-provider or final R5 qualification.')),
    (('HST-022', 'HST-031'), evidence(
        '92529cf4d4d3660ac98e1c415fb60151aefaa9a7',
        'Fresh R4 wheel build/install/smoke, exact four-artifact Twine and live HTTP/MCP',
        'PASS build/install/live; 54 tools, two authenticated identities; canonical stop0 and physical exit0',
        'execution/package-hst-r4/live-qualification.json',
        'No provider. R4 backend payload1024 files exactly equal R3 (729 Nexus/168 Core/127 Connector); '
        'R3 tests reused only in that scope. R4 UI requires its own browser checks.')),
    (('HST-018', 'HST-019', 'HST-020', 'HST-021', 'HST-022', 'HST-026', 'HST-028'), evidence(
        '042585b4c622948261a50b550fec3616e2743e45',
        'Real Chromium against isolated installed R3; exact sessions, two unchanged polls, partial source and logout',
        'PASS_SUBSET21; no productive browser POST; normal cleanup',
        'execution/browser-hst/cuts/r3-reading-partial-logout/qualification.json',
        'Fixture, not a real harness. Keyboard/mobile assertions are a subset, not a screen-reader or novice-user test. '
        'Final R4/R5 UI still requires qualification.')),
    (('HST-011', 'HST-012', 'HST-017', 'HST-028'), evidence(
        '042585b4c622948261a50b550fec3616e2743e45',
        'Canonical authenticated claim, completion and verification with same exact delivery/op; browser at each stage',
        'PASS_SUBSET15: turn result/task open, awaiting verification, exact delivery verified',
        'execution/browser-hst/cuts/r3-governed-result/qualification.json',
        'Inert native peer, not provider inference. No assertion that every Results criterion is covered.')),
    (('HST-006', 'HST-007', 'HST-008', 'HST-016', 'HST-028'), evidence(
        '042585b4c622948261a50b550fec3616e2743e45',
        'Canonical native question plus independent submitted/started operation; explicit browser answer202',
        'PASS_SUBSET14, FAIL1: actual Working producer mismatch; decision registered remains awaiting confirmation',
        'execution/browser-hst/cuts/r3-question-decision/qualification.json',
        'Core keeps receipt SUBMITTED while current progress exists. R5 correction in progress; '
        'no fabricated RUNNING receipt. Post-answer terminal cut not qualified; causal APPLIED proof unavailable.')),
]
for task_ids, entry in cuts:
    for task in ledger['tasks']:
        if task['id'] in task_ids and not any(
                old.get('artifact_path') == entry['artifact_path'] for old in task['evidence']):
            task['evidence'].append(entry)
ledger['execution']['r3_source']['installed_browser_performance'] = (
    'Installed PASS746/SKIP8; browser scoped positives plus Working producer FAIL; final performance pending')
ledger['execution']['package_r4'] = {
    'source_commit': '92529cf4d4d3660ac98e1c415fb60151aefaa9a7',
    'wheel_sha256': '9204183fcb00628b311f417d9cc601bbc6060f2c1347d200cf433cb8e32773a8',
    'ready': 'execution/package-hst-r4/READY.json',
    'build_install_smoke_live': 'PASS',
    'runtime_equivalence': 'execution/package-hst-r4/runtime-equivalence-vs-r3.json',
    'pytest_r4_executed': False,
    'ui_browser': 'PENDING',
}
ledger['execution']['r5_working_correction'] = {
    'status': 'IN_PROGRESS',
    'cause': 'Actual committed started/progress exists while Core receipt remains SUBMITTED.',
    'approach': 'Private full-key positive proof; preserve authority/liveness/gap/uncertainty and terminal fences.',
    'receipt_core_schema_changes': False,
    'final_qualification': 'PENDING',
}
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
