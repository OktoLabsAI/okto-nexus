"""Run final finite gate checks with own benign base-Python handle only."""
from pathlib import Path
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).parent / 'draft'
I = ROOT/'installation'
env=json.loads((I/'environment.json').read_text())
env['__PYVENV_LAUNCHER__']=str(I/'venv/Scripts/python.exe')
env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
files=list(ROOT.glob('*.py'))+list((ROOT/'controller').glob('*.py'))+list(I.glob('*.py'))
files += [ROOT/'m1-codex-campaign-proposal-v9.json',ROOT/'proposed-commands.json']
def hashes():
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
before=hashes()
with (ROOT/'final-gates.stdout.txt').open('xb') as out,(ROOT/'final-gates.stderr.txt').open('xb') as err:
    process=subprocess.Popen(['C:/Python313/python.exe','-I','-B',str(ROOT/'run_final_gates.py')],
        env=env,cwd=I/'isolated',stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    print(json.dumps({'own_python_pid':process.pid,'scope':'27 pure installer gates plus 12 entry denials'}),flush=True)
    code=process.wait()
after=hashes()
tree=ET.parse(ROOT/'final-gates.xml')
counts={'cases':len(list(tree.iter('testcase'))),'failures':len(list(tree.iter('failure'))),
        'errors':len(list(tree.iter('error'))),'skips':len(list(tree.iter('skipped')))}
entry=json.loads((ROOT/'guard-result.json').read_text())
passed=(code==0 and before==after and counts=={'cases':27,'failures':0,'errors':0,'skips':0}
        and entry['unique_cases']==12 and entry['effects']=={'popen':0,'socket':0,'vault':0})
report={'status':'PASS' if passed else 'FAILED_RETAINED','returncode':code,'tests':counts,
        'entry_denials':12,'entry_effects':entry['effects'],'inputs_unchanged':before==after,
        'input_hashes_before':before,'input_hashes_after':after,
        'products_installed':False,'campaign_root_created':False,
        'limits':'Pure installer/receipt guards and denied entry paths only, no product/provider/native/service/credential API execution.'}
(ROOT/'final-gates-result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ('status','returncode','tests','entry_denials','inputs_unchanged')}))
raise SystemExit(0 if passed else 1)
