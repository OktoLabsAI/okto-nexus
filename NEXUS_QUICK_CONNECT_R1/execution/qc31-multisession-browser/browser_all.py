"""One finite own browser sequence; close before signaling fixture stop."""
import json
from pathlib import Path
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
allocation=json.loads((HERE/'allocation.json').read_text())
root=Path(allocation['root'])
until=time.monotonic()+180
while not Path(allocation['ready']).exists():
    assert not (root/'control/failure.json').exists(), 'Fixture failed before browser readiness'
    assert time.monotonic()<until, 'No ready fixture within setup deadline'
    time.sleep(.2)
ready=json.loads(Path(allocation['ready']).read_text())
(HERE/'ready.json').write_text(json.dumps(ready,indent=2)+'\n')
for source,target in [('initialize-template.js','initialize.js'),('checks-template.js','checks.js')]:
    (HERE/target).write_text((HERE/source).read_text().replace('__CFG__',json.dumps(ready)),encoding='utf-8')
(REPO/'output/playwright/qc31').mkdir(parents=True,exist_ok=True)
prefix=[shutil.which('rtk'),'proxy','C:/Program Files/nodejs/npx.cmd','--yes','--package','@playwright/cli','playwright-cli','--session=qc31-multisession']
records=[]
def run(label,tail):
    argv=[*prefix,*tail]
    # The CLI daemon can inherit output handles. A regular file avoids waiting
    # for pipe EOF after the direct CLI process has already exited.
    log_path=root/(label+'-cli.log')
    with log_path.open('w',encoding='utf-8') as log:
        result=subprocess.run(argv,cwd=REPO,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=70)
    output=log_path.read_text(encoding='utf-8')
    records.append(dict(label=label,argv=argv,exit_code=result.returncode))
    if label=='checks' and '### Result\n' in output:
        value,_=json.JSONDecoder().raw_decode(output.split('### Result\n',1)[1])
        (root/'checks-result.json').write_text(json.dumps(value,indent=2)+'\n')
        print(json.dumps(dict(status=value['status'],checks=value['checks'])),flush=True)
    assert result.returncode==0,label
try:
    run('open',['open','about:blank','--browser','chrome','--profile',str(root/'browser-profile'),'--persistent','--idle-timeout','180000'])
    run('initialize',['run-code','--filename',str(HERE/'initialize.js')])
    run('snapshot',['snapshot'])
    run('checks',['run-code','--filename',str(HERE/'checks.js')])
    run('requests',['requests'])
finally:
    run('close',['close'])
    Path(allocation['stop']).touch()
    (root/'browser-commands.json').write_text(json.dumps(records,indent=2)+'\n')
