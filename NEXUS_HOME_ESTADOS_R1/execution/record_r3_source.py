"""Record corrected canonical readiness and scoped source regression evidence."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
d = json.loads(path.read_text(encoding='utf-8'))
e = {
    'commit': 'a6e08b6f82a3afb7641b6f1ff2a4855fc1695d41 + exact R3 source/test artifact pins',
    'command_or_procedure': 'Bounded isolated source Home regression, including 33 SQL and 4 canonical ingress cases',
    'environment': 'Windows; source-only Nexus with pinned installed dependencies and inert native peer',
    'timestamp': datetime.now(UTC).isoformat(),
    'result': 'PASS215; source/test drift0; no timeout/force/remaining known processes. Focals separately PASS37.',
    'artifact_path': 'execution/source-tests/r3-home/qualification.json',
    'limitations': 'R3 installed/browser/performance not qualified yet. Prior R2 browser failure and capacity misses retained. Initial R3 fixture gap was unfillable and contained; final fixture uses real journal sequences and canonical recovery.',
}
for task in d['tasks']:
    if task['id'] in ('HST-002', 'HST-005', 'HST-006', 'HST-007', 'HST-010', 'HST-024', 'HST-025', 'HST-027'):
        task['evidence'].append(e)
        if task['id'] == 'HST-002':
            task['status'] = 'VERIFIED'
        elif task['id'] in ('HST-005', 'HST-006', 'HST-007', 'HST-010'):
            task['status'] = 'IMPLEMENTED'
d['execution']['r3_source'] = {
    'source_regression': 'PASS215', 'focals': 'PASS37', 'source_test_drift': [],
    'proof_correction': 'Use the actual atomic committed-ingress projection contract; exclude committed current-stream failure; never use unwritten projected_through as readiness.',
    'performance_change': 'Batch complete progress keys by eligible full session/epoch; preserve correlated fallback for malformed legacy JSON.',
    'schema_migration': False, 'core_or_protocol_changes': False,
    'package_directory': 'execution/package-hst-r3', 'installed_browser_performance': 'NOT_RUN',
    'human': 'DEFERRED_UNTIL_OUR_IMPLEMENTATION_AND_CHECKS_READY',
}
path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
