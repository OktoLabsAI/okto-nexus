import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
allocation=json.loads((HERE/'allocation.json').read_text())
root=Path(allocation['root'])
action=sys.argv[1]
if action=='checks':
    (REPO/'output/playwright/qc31').mkdir(parents=True,exist_ok=True)
    (HERE/'checks.js').write_text((HERE/'checks-template.js').read_text().replace('__CFG__',(HERE/'ready.json').read_text()),encoding='utf-8')
    tail=['run-code','--filename',str(HERE/'checks.js')]
else:
    tail=[action]
argv=[shutil.which('rtk'),'proxy','C:/Program Files/nodejs/npx.cmd','--yes','--package','@playwright/cli','playwright-cli','--session=qc31-multisession',*tail]
result=subprocess.run(argv,cwd=REPO,stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',timeout=70)
(root/(action+'-cli.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
if action=='checks' and '### Result\n' in result.stdout:
    value,_=json.JSONDecoder().raw_decode(result.stdout.split('### Result\n',1)[1])
    (root/'checks-result.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value,ensure_ascii=True))
else:
    print(result.stdout)
raise SystemExit(result.returncode)
