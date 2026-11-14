"""One reviewed revision17 step; preserve history and require exact frozen files."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-revision17')
FREEZE = '5dba520a68d87cf71dd9135b0d73dba0e6b1283515ff96246369f3e558cfb9c4'
digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert digest(ROOT / 'runtime-freeze.json') == FREEZE
freeze = json.loads((ROOT / 'runtime-freeze.json').read_bytes())
assert all(digest(pin['path']) == pin['sha256'] for pin in freeze['files'].values())
workflow = json.loads((ROOT / 'workflow.json').read_bytes())
assert len(sys.argv) == 2
step = next(s for s in workflow['steps'] if s['label'] == sys.argv[1])
raise SystemExit(subprocess.call(step['argv'], cwd=ROOT))
