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
for stage in ledger['stages']:
    if stage['id'] in ('HST-02', 'HST-03'):
        stage['status'] = 'IN_PROGRESS'
ledger['execution']['source_regression'] = dict(result='PASS368',
    artifact='execution/source-tests/home-global/qualification.json',
    limitations='Pre-currentness delta; SOURCE_ONLY, not final package/browser/real harness.')
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
