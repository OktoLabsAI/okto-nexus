"""Own benign Python only; never installs or invokes campaign commands."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path(__file__).parent/'draft'
env=json.loads((ROOT/'installation/environment.json').read_text())
env['__PYVENV_LAUNCHER__']=str(ROOT/'installation/venv/Scripts/python.exe')
files=[ROOT/'m1-codex-campaign-proposal-v9.json',ROOT/'campaign_context.py',ROOT/'test_entry_guards.py',ROOT/'check_restored_python_pin.py']
def hashes(): return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
before=hashes()
with (ROOT/'interpreter-pin-gates.stdout.txt').open('xb') as out,(ROOT/'interpreter-pin-gates.stderr.txt').open('xb') as err:
    process=subprocess.Popen(['C:/Python313/python.exe','-I','-B',str(ROOT/'check_restored_python_pin.py')],
        env=env,cwd=ROOT/'installation/isolated',stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    print(json.dumps({'owned_python_pid':process.pid,'scope':'pure interpreter-pin regression + entry denials'}),flush=True)
    code=process.wait()
after=hashes()
report={'status':'PASS' if code==0 and before==after else 'FAILED_RETAINED','returncode':code,
 'input_hashes_before':before,'input_hashes_after':after,'inputs_unchanged':before==after,
 'campaign_or_installation_executed':False}
(ROOT/'interpreter-pin-check-execution.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'returncode':code}))
raise SystemExit(code)
