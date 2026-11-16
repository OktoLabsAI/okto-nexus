"""Observe the real driver entry point refusing absent consent before effects."""
import contextlib
import io
import json
from pathlib import Path
import runpy
import sys

BASE=Path('C:/Users/jpamb/AppData/Local/Temp/home-r1-local-driver-6t4xonw6')
SHA='6181fd0029f1eb023d226f168f6d00b60baad2cfe92e12b3850592a36fecc189'
root=Path('C:/Users/jpamb/AppData/Local/Temp/home-r1-local-codex-bc1d3f18e856')
assert not root.exists() and not list(BASE.glob('*authorization*'))
state={'guard':True,'product_import_attempts':[],'effect_attempts':[]}


def audit(event,args):
    if not state['guard']:return
    if event=='import' and str(args[0]).startswith(('okto_nexus','nexus_connector_core')):
        state['product_import_attempts'].append(str(args[0]))
        raise AssertionError('PRODUCT_IMPORT_BEFORE_CONSENT')
    if event in ('subprocess.Popen','os.mkdir','os.system'):
        state['effect_attempts'].append(event)
        raise AssertionError('EFFECT_BEFORE_CONSENT')
    if event=='open' and str(args[0]).replace('\\','/').lower().startswith('c:/users/jpamb/.codex/'):
        state['effect_attempts'].append('provider_home_open')
        raise AssertionError('PROVIDER_HOME_READ_BEFORE_CONSENT')


sys.addaudithook(audit)
sys.argv=[str(BASE/'driver.py'),'--plan',str(BASE/'candidate-server-final.json'),'--plan-sha256',SHA,'prepare']
captured=io.StringIO()
exit_code=None
with contextlib.redirect_stdout(captured):
    try:runpy.run_path(str(BASE/'driver.py'),run_name='__main__')
    except SystemExit as error:exit_code=error.code
state['guard']=False
result=json.loads(captured.getvalue().strip())
assert exit_code==1 and result['code']=='NEW_PAID_CONSENT_REQUIRED',result
assert not state['product_import_attempts'] and not state['effect_attempts']
assert not any(m.startswith(('okto_nexus','nexus_connector_core')) for m in sys.modules)
assert not root.exists() and not list(BASE.glob('*authorization*'))
proof={'status':'PASS_REFUSED_BEFORE_PRODUCT_IMPORT_OR_EFFECTS','candidate_sha256':SHA,
    'driver_exit_code':exit_code,'driver_result':result,'product_import_attempts':[],
    'effect_attempts':[],'product_modules_loaded':False,'campaign_root_exists':False,
    'authorization_exists':False,'reservations':0,'provider_calls':0,
    'method':'Actual driver.py __main__ via runpy with original CLI argv and an audit hook that would fail any product import, process/directory effect or provider-home read before consent. No product/driver function replaced.'}
with (BASE/'refusal-server-result.json').open('x',encoding='utf-8') as stream:
    json.dump(proof,stream,indent=2);stream.write('\n')
print(json.dumps(proof))
