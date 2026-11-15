"""Root launcher for the frozen phase1, with explicit isolated import path."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

ROOT = Path('C:/Users/jpamb/AppData/Local/Temp/m1-sonnet-remote-candidate-2c_4af0t')
FREEZE = '5e702cdcef6a4e79e41947d05f2d8ac775af359ef4ef248298a25fa4d3fbdf37'
PLAN = '9c134a2dd806cf3a173b8c4a0e55f97a00dc6713f94746cf804be914733d658b'
ACTIONS = {'prepare', 'install', 'start', 'select', 'watch', 'bootstrap', 'stop', 'cleanup', 'uninstall'}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

assert len(sys.argv) == 2 and sys.argv[1] in ACTIONS, 'ACTION_INVALID'
action = sys.argv[1]
freeze = ROOT / 'phase1-freeze.json'
assert sha(freeze) == FREEZE, 'FREEZE_CHANGED'
for entry in json.loads(freeze.read_bytes())['files'].values():
    assert sha(Path(entry['path'])) == entry['sha256'], 'FROZEN_FILE_CHANGED'
with (ROOT / ('phase1-launch-' + action + '.json')).open('x', encoding='utf-8') as record:
    json.dump({'action': action, 'freeze_sha256': FREEZE, 'plan_sha256': PLAN,
               'launcher_sha256': sha(Path(__file__)), 'explicit_import_root': str(ROOT),
               'original_direct_prepare_failed_before_import': 'tool69ccc9 ModuleNotFoundError request_context'}, record, indent=2)
sys.path.insert(0, str(ROOT))
sys.argv = [str(ROOT / 'phase1.py'), '--plan', str(ROOT / 'phase1-plan.json'),
            '--expected-plan-sha256', PLAN, action]
runpy.run_path(str(ROOT / 'phase1.py'), run_name='__main__')
