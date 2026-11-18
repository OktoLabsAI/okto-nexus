"""Record source/build implementation while preserving the real failing browser gate."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
q = json.loads((HERE / 'frontend-r9-focus/qualification.json').read_text())
assert q['status'] == 'PASS' and q['input_drift'] == []
assert all(step['success'] for step in q['steps'].values())
assert 'pass 404' in (HERE / 'frontend-r9-focus/node.log').read_text(encoding='utf-8')
assert 'assets/index-ZSaBIkKg.js' in q['static_assets']
path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger = json.loads(path.read_text(encoding='utf-8'))
assert all(test['status'] == 'FAIL' for test in ledger['tests'] if test['id'] in ('HST-T-F07', 'HST-T-I02'))
ledger['execution']['r9_focus_source'] = {'status': 'IMPLEMENTED_NOT_VERIFIED',
    'source_change': 'OperationalHome.close publishes the cached presentation through pause(manualPause) before removing the panel and scheduling focus; callback depends on manualPause and stable pause',
    'manual_pause_preserved': True, 'backend_source_changed': False,
    'frontend': 'execution/frontend-r9-focus/qualification.json',
    'original_checkout': True, 'node': '404PASS', 'typescript_vite': 'PASS',
    'input_drift': [], 'bundle': 'assets/index-ZSaBIkKg.js', 'css': 'assets/index-Bh2ghaTD.css',
    'source_commit': 'To be bound by execution/package-hst-r9/SOURCE_ASSET_READY.json after commit',
    'installed': 'PENDING_NEW_R9_PREFIX', 'browser': 'PENDING_SAME_CANONICAL_MOVE_FOCUS_PREDICATE',
    'human': 'NOT_INVITED', 'default_approved': False}
ledger['execution']['r8_focus_regression']['source_fix'] = 'R9 implemented; Node404/TSC/Vite pass, installed browser proof pending'
ledger['execution']['local_usability_candidate']['state'] = 'NOT_READY: R9 focus source correction implemented, fresh installed/browser regression proof pending'
path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(ledger['execution']['r9_focus_source']))
