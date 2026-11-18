"""Root-owned evidence reconciliation, never a promotion of unrun scenarios."""
from datetime import datetime, timezone
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
now = datetime.now(timezone.utc).isoformat()


def record(ids, procedure, result, artifact, limitations):
    for task in ledger['tasks']:
        if task['id'] not in ids:
            continue
        task['status'] = 'IMPLEMENTED'
        evidence = dict(commit='8b4001fa1db17bf29d0c773eed3535e79fce70cb + scoped working-tree payload pinned by artifact',
                        command_or_procedure=procedure,
                        environment='Windows; isolated source-only Python/Node, no provider or personal installation',
                        timestamp=now, result=result, artifact_path=artifact, limitations=limitations)
        if not any(item['artifact_path'] == artifact for item in task['evidence']):
            task['evidence'].append(evidence)


record(['HST-011', 'HST-012', 'HST-013'],
       'Focused delivery domain/SQLite/canonical verification and legacy results tests',
       'PASS58 focused source tests; expanded source regression PASS368 before operational currentness delta',
       'execution/delivery-implementation/final/qualification.json',
       'Not installed HTTP/browser/harness qualification; legacy proofs without exact reference remain unknown; full scenario acceptance pending.')
record(['HST-003'], 'Real router/HTTP read UoW negotiation and strict Node contracts',
       'PASS explicit v1/v2 capability negotiation; invalid/repeated parameters rejected; protected tables unchanged',
       'execution/source-tests/negotiation/qualification.json',
       'Synthetic isolated project; not final installed or browser compatibility qualification.')
record(['HST-014', 'HST-015', 'HST-016', 'HST-017', 'HST-023'],
       'npm test (contract/controller/SSR presentation suite)',
       'PASS401 Node tests; normative labels and current action links covered',
       'execution/frontend-global/qualification.json',
       'Node/SSR is not browser, assistive technology or human usability; final installed/browser scenarios pending.')
record(['HST-018', 'HST-019', 'HST-020', 'HST-021'],
       'Node exact-context, controller, pagination and selection tests; TypeScript',
       'PASS73 interaction tests and TypeScript; exact targets and revision resync covered',
       'execution/hst04-context/qualification.json',
       'Focus, draft and two-cycle polling acceptance still requires final real browser checks.')
record(['HST-005', 'HST-006', 'HST-007', 'HST-008', 'HST-009', 'HST-010', 'HST-022'],
       'Operational domain/board, canonical SQLite/ASGI HTTP, currentness negative cases',
       'PASS40 focused source tests after currentness fences; no provider executed',
       'execution/operational-currentness/qualification.json',
       'End pins only for this cut; earlier audit retained. Positive native causal resume D08 lacks producer evidence. Installed/browser/performance acceptance pending.')
for item in ledger['tasks']:
    if item['id'] == 'HST-008':
        item['status'] = 'BLOCKED'
    if item['id'] in ('HST-024', 'HST-025', 'HST-031'):
        item['status'] = 'IN_PROGRESS'
    if item['id'] == 'HST-029':
        item['status'] = 'BLOCKED'
        item['evidence'] = [dict(commit='5f7b7059 + scoped candidate awaiting package',
            command_or_procedure='Inspect campaign consent, provider contracts and retained Quick Connect usage gate',
            environment='Static review; no provider or credentials accessed', timestamp=now,
            result='BLOCKED: no HOME-STATES-R1 real campaign proposal/budget approved; prior authorizations are not reused',
            artifact_path='execution/source-proof-map.md',
            limitations='Codex/Pi/Claude and multi-host real qualification not performed; prior UNKNOWN usage blockers retained.')]
for item in ledger['tests']:
    if item['id'] == 'HST-T-D08':
        item['status'] = 'BLOCKED'
        item['evidence'] = [dict(commit='5f7b7059 + currentness working tree pins',
            command_or_procedure='Producer contract review and negative late-RUNNING/decision tests',
            environment='Source-only; no real provider', timestamp=now,
            result='BLOCKED positive causal application/resume: producer provides write receipt, not an application acknowledgment',
            artifact_path='execution/operational-currentness/qualification.json',
            limitations='Conservative awaiting/unknown implemented; late event arrival is deliberately not treated as proof.')]
    if item['id'].startswith('HST-T-L'):
        item['status'] = 'BLOCKED'
        item['evidence'] = next(t for t in ledger['tasks'] if t['id'] == 'HST-029')['evidence']
for stage in ledger['stages']:
    if stage['id'] in ('HST-02', 'HST-03'):
        stage['status'] = 'IN_PROGRESS'
    if stage['id'] in ('HST-05', 'HST-06'):
        stage['status'] = 'IN_PROGRESS'
ledger['execution']['source_regression'] = dict(result='PASS368',
    artifact='execution/source-tests/home-global/qualification.json',
    limitations='Pre-currentness delta; SOURCE_ONLY, not final package/browser/real harness.')
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
