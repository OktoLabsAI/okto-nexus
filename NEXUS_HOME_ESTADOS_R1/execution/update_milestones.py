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
for stage in ledger['stages']:
    if stage['id'] == 'HST-02':
        stage['status'] = 'IN_PROGRESS'
ledger['execution']['source_regression'] = dict(result='PASS368',
    artifact='execution/source-tests/home-global/qualification.json',
    limitations='Pre-currentness delta; SOURCE_ONLY, not final package/browser/real harness.')
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
