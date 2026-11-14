"""One reviewed revision16 step; preserve history and require exact frozen files."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-revision16')
FREEZE = 'fdcfab39cf9445c70878dfaf8f1bec3964b2debbf2c2e1ea857ba8496ccc1e94'
digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert digest(ROOT / 'runtime-freeze.json') == FREEZE
freeze = json.loads((ROOT / 'runtime-freeze.json').read_bytes())
assert all(digest(pin['path']) == pin['sha256'] for pin in freeze['files'].values())
workflow = json.loads((ROOT / 'workflow.json').read_bytes())
assert len(sys.argv) == 2
step = next(s for s in workflow['steps'] if s['label'] == sys.argv[1])
raise SystemExit(subprocess.call(step['argv'], cwd=ROOT))
