"""Canonical installed environment inspection only; no lifecycle or provider selection."""
from pathlib import Path
import hashlib,json,sys,time
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
installed=json.loads((HERE/'package/installation.json').read_bytes())
assert Path(sys.prefix)==Path(installed['python_prefix'])
agreement={}
for component,module in [('nexus','okto_nexus'),('connector','okto_nexus_connector')]:
    source=HERE/'package'/(component+'-source')/'src'/module/'service_environment.py'
    target=Path(sys.prefix)/'Lib/site-packages'/module/'service_environment.py'
    assert source.read_bytes()==target.read_bytes()
    agreement[component]={'source_sha256':sha(source),'installed_sha256':sha(target)}
from okto_nexus.service_environment import probe
started=time.monotonic()
try:
    candidate=probe(installed['python'])
    elapsed=time.monotonic()-started
    assert candidate['executable']==installed['python'] and candidate['environment_prefix']==installed['python_prefix']
    assert candidate['package']['version']=='0.3.3' and candidate['core']['version']=='0.0.14'
    assert elapsed<60
    value={'status':'CANONICAL_PROBE60_PASS','elapsed_seconds':elapsed,'canonical_probe_timeout_seconds':60,
        'candidate':candidate,'source_installed_agreement':agreement,'installation_sha256':sha(HERE/'package/installation.json'),
        'python':sys.executable,'prefix':sys.prefix,'model_calls':0,'service_actions':0,'upgrade_actions':0,
        'scope':'Installed canonical service_environment.probe only; no runtime home, Scheduler or provider touched.'}
except BaseException as error:
    value={'status':'CANONICAL_PROBE60_FAILED','elapsed_seconds':time.monotonic()-started,
        'error_type':type(error).__name__,'error_code':getattr(error,'code',None),
        'source_installed_agreement':agreement,'model_calls':0,'service_actions':0,'upgrade_actions':0}
    with (HERE/'probe-qualification.json').open('x',encoding='utf-8') as out:json.dump(value,out,indent=2)
    raise
with (HERE/'probe-qualification.json').open('x',encoding='utf-8') as out:json.dump(value,out,indent=2)
print(json.dumps({'status':value['status'],'elapsed_seconds':elapsed,'qualification_sha256':sha(HERE/'probe-qualification.json')}))
