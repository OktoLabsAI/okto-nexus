"""Preserve package success, capacity misses and the browser proof regression."""
from datetime import UTC, datetime
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
d = json.loads(path.read_text(encoding='utf-8'))
at = datetime.now(UTC).isoformat()


def item(artifact, result, procedure, limitations):
    return {'commit': '4e890949c94c9d8625837d566e5182920bfb2cec',
            'command_or_procedure': procedure, 'environment': 'Windows; isolated installed R2, no provider',
            'timestamp': at, 'result': result, 'artifact_path': artifact, 'limitations': limitations}


perf = item('execution/performance-hst/persistent-r2-final/qualification.json',
            'FAIL target500ms: all8 large cuts; PASS target500ms all6 small cuts; all14 complete/exited',
            'Persistent ASGI paired installed cuts, 3 warmups and 20 samples per route',
            'First useful browser DOM remains NOT_RUN; improvement in paired R2v2 series does not waive capacity target or prove v1 improvement.')
browser = item('execution/browser-hst/antecedents/r2-unprojected-watermark/qualification.json',
               'FAIL B02: canonical events materialized but Home readiness required an unwritten watermark; timing NOT_QUALIFIED',
               'Canonical inert Core preflight followed by real browser, 44 GETs/0 POSTs; normal cleanup',
               'No journey PASS, real provider or human usability claimed; reader correction and new canonical-ingress regression in progress.')
for task in d['tasks']:
    if task['id'] in ('HST-027',):
        task['evidence'].append(perf)
    if task['id'] in ('HST-002', 'HST-005', 'HST-007', 'HST-026', 'HST-028'):
        task['status'] = 'IN_PROGRESS'
        task['evidence'].append(browser)
for test in d['tests']:
    if test['id'] == 'HST-T-J04':
        test['status'] = 'FAIL'
        test['evidence'].append(perf)
    if test['id'] == 'HST-T-J05':
        test['status'] = 'PASS'
        test['evidence'].append(item(perf['artifact_path'],
            'PASS comparable paired datasets, raw samples/p50/p95/query counts/bytes/origins recorded; latency target separately FAIL',
            perf['command_or_procedure'], perf['limitations']))
    if test['id'] == 'HST-T-B02':
        test['status'] = 'FAIL'
        test['evidence'].append(browser)
d['execution']['performance_r2']['new_performance_qualification'] = 'FAIL_TARGET500MS_LARGE_CASES'
d['execution']['performance_r2']['browser'] = 'BLOCKED_PRODUCT_READINESS_PROOF_MISMATCH'
d['execution']['package_r2'] = {
    'ready': 'execution/package-hst-r2/READY.json',
    'source_commit': '4e890949c94c9d8625837d566e5182920bfb2cec',
    'wheel_sha256': '14ca237285cd2ecee516f1b0df8cbff8277466ca6160e696f49867d077021560',
    'payload_files': 1031, 'source_pins': 1818, 'payload_and_source_drift': [],
    'live_mcp': 'PASS canonical stop0 and physical exit0',
    'limitation': 'Package READY is not feature qualification; R2 browser proof bug remains an antecedent failure.',
}
path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
