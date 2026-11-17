"""Record the optimization source cut without promoting performance or browser."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
d = json.loads(path.read_text(encoding='utf-8'))
at = datetime.now(UTC).isoformat()
evidence = {
    'commit': 'b04799c6 + exact source/test payload pins in artifact',
    'command_or_procedure': 'Isolated source Home suites, including batch/revision equivalence oracles',
    'environment': 'Windows; source-only Nexus with pinned installed dependencies; no provider',
    'timestamp': at, 'result': 'PASS178; source/test drift zero; 35 batch/revision cases included',
    'artifact_path': 'execution/source-tests/perf-r2-home/qualification.json',
    'limitations': 'New package and performance repeat pending. Initial focal cut retained as 31PASS/2FAIL caused by unavailable fixture workspace; explicit unavailable-workspace authority negatives now pass.',
}
for task in d['tasks']:
    if task['id'] in ('HST-010', 'HST-024', 'HST-025', 'HST-027'):
        task['evidence'].append(evidence)
        if task['id'] != 'HST-010':
            task['status'] = 'IN_PROGRESS'
for test in d['tests']:
    if test['id'] in ('HST-T-J04', 'HST-T-J05'):
        test['status'] = 'FAIL'
        test['evidence'] = [{
            'commit': '687295b6cd6758aa36690152fdb4258e36d33c91',
            'command_or_procedure': '12 paired installed ASGI/TestClient cuts; 3 warmups and 20 samples per route',
            'environment': 'Windows; baseline 0.3.6 and first frozen 0.3.7, owned byte-identical datasets',
            'timestamp': at, 'result': 'Valid complete replies, 500ms p95 miss at 100 connections; FAIL retained',
            'artifact_path': 'execution/performance-hst/original-qualification.json',
            'limitations': 'Mixed retained and explicit 1000OPEN workloads distinguished. Fresh TestClient portal per request; persistent transport refinement and optimized candidate not measured yet. DOM first-useful NOT_RUN.',
        }]
d['execution']['performance_r2'] = {
    'source_tests': 'PASS178', 'source_test_drift': [],
    'artifact': evidence['artifact_path'], 'original_target_500ms': 'FAIL',
    'fresh_package_directory': 'execution/package-hst-r2',
    'new_performance_qualification': 'NOT_RUN', 'browser': 'NOT_RUN',
}
path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
