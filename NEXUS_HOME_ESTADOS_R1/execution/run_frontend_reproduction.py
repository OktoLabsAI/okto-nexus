"""One bounded Node reproduction; expected red is evidence, not an acceptance PASS."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
out=HERE/'frontend-reproduction'
argv=[shutil.which('rtk'),'proxy',shutil.which('node'),'--test',str(out/'reproduction.mjs')]
started=datetime.now(timezone.utc).isoformat()
with (out/'node.log').open('w',encoding='utf-8') as log:
    result=subprocess.run(argv,cwd=REPO,input='',stdout=log,stderr=subprocess.STDOUT,text=True,timeout=30)
pins=json.loads((out/'source-pins.json').read_text())
drift=[p for p,h in pins.items() if hashlib.sha256((REPO/p).read_bytes()).hexdigest()!=h['sha256']]
record=dict(argv=argv,started_at=started,ended_at=datetime.now(timezone.utc).isoformat(),exit_code=result.returncode,
    expected_exit=1,source_drift=drift,scope='Controlled Node only; no HTTP/SQLite/browser/provider/user qualification.')
(out/'run.json').write_text(json.dumps(record,indent=2)+'\n')
assert result.returncode==1 and not drift
print(json.dumps(record))
