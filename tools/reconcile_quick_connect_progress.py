"""Explicit implementation milestone annotations, separate from qualification."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / 'NEXUS_QUICK_CONNECT_R1'
CANDIDATE = 'a0fa79129d8760eef945fc1445c2355430d5b54c'
MILESTONES = [
    (['QC-002', 'QC-004', 'QC-005', 'QC-009', 'QC-010'], 'execution/qc06-foundation-security/qualification.json',
        'Current pure contracts, grammar, dispatch, local Git and project decisions; 260 source-level checks. Installed and native qualification separate.'),
    (['QC-006', 'QC-007'], 'execution/evidence/qc03-harness-alternatives/qualification.json',
        'Explicit supported-family alternatives and policy/freshness fences; source CLI plus inert HTTP. No real provider readiness claim.'),
    (['QC-008', 'QC-026'], 'execution/qc05-frontend/qualification.json',
        'Additive public ID vocabulary and projections; 360 Node tests and TypeScript/Vite. Browser limitations retained separately.'),
    (['QC-011', 'QC-014', 'QC-015', 'QC-017', 'QC-018'], 'execution/qc03-backend/qualification.json',
        'Authorized directory, canonical proof, persistent registry and atomic setup/receipt with fixed legacy digest. Faults and concurrency are synthetic HTTP/SQLite.'),
    (['QC-012', 'QC-013', 'QC-016', 'QC-020', 'QC-021', 'QC-022', 'QC-023', 'QC-024'],
        'execution/evidence/qc04-cli-http/qualification.json',
        'Managed first/second connection, canonical resume, collision, recovery and customization implemented and tested with inert peers; later focused deltas supersede relevant source pins.'),
    (['QC-019'], 'execution/qc07-public-id-occupancy/qualification.json',
        'Canonical disable preserves occupied public ID; old-timestamp reservation remains unavailable. No automatic cleanup or native termination asserted.'),
    (['QC-025', 'QC-027', 'QC-028'], 'execution/qc04-terminal/qualification.json',
        'Commit recovery, local shortcut repair, metadata adoption and remote canonical scope. Full installed regressions remain in progress.'),
    (['QC-032'], 'execution/baseline.md',
        'Guide docs/quick-connect.md at 0a1cbaba documents tested syntax, authority, partial outcomes and presentation rollback.'),
]


def main():
    target = BASE / 'NEXUS_QUICK_CONNECT_LEDGER_R1.json'
    ledger = json.loads(target.read_text('utf-8'))
    tasks = {row['id']: row for row in ledger['tasks']}
    for ids, path, scope in MILESTONES:
        assert (BASE / path).is_file(), path
        for identity in ids:
            task = tasks[identity]
            if task['status'] != 'VERIFIED':
                task['status'] = 'IMPLEMENTED'
            evidence = dict(path=path, scope=scope, commit=CANDIDATE)
            if evidence not in task['evidence']:
                task['evidence'].append(evidence)
    for identity in ('QC-029', 'QC-030', 'QC-033'):
        tasks[identity]['status'] = 'IN_PROGRESS'
    tasks['QC-031']['status'] = 'BLOCKED'
    tasks['QC-031']['evidence'] = [dict(path='execution/coverage-review.json', commit=CANDIDATE,
        scope='A new real-provider campaign needs its own consent/budget and resolution of the retained UNKNOWN usage guard; no new provider call made.')]
    tasks['QC-031']['execution_notes'] = 'Implementation work continues independently; synthetic/native-PTY/installed tests do not clear the real-campaign gate.'
    ledger['execution'] = dict(candidate=CANDIDATE, branch='feature/v0.3.6', version='0.3.6',
        draft_pr='https://github.com/OktoLabsAI/okto-nexus/pull/139',
        implementation_gate='IN_PROGRESS: installed regression and final matrix reconciliation',
        real_qualification_gate='BLOCKED: fresh campaign consent and prior UNKNOWN usage guard',
        limitations=['UI-R1 original qualification ledger and prior human failures remain unchanged.',
            'No further human testing, Windows session events, personal install changes or paid provider runs.',
            'Browser malformed historical viewer and unattributed sessions digest change retained as limits.',
            'PTY Ctrl-C interrupted the tool transport; checkpoint survived, CLI return-130 not qualified.'])
    target.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({state: sum(row['status'] == state for row in tasks.values())
        for state in sorted({row['status'] for row in tasks.values()})}))


if __name__ == '__main__':
    main()
