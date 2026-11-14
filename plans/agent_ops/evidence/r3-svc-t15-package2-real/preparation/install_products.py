"""Offline package2 wheel copy/install in own venv; no product CLI."""
from pathlib import Path
import hashlib,json,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
inputs=json.loads((ROOT/'wheel-inputs.json').read_bytes())
assert set(inputs)=={'nexus','core','connector'}
assert inputs['core']['sha256']=='d881ab35ac619147df51cbe3a10964e534c50acd117e45e2612dcec7fbc1afe9'
(ROOT/'wheels').mkdir()
wheels=[]
for name,pin in inputs.items():
    source=Path(pin['path']);assert sha(source)==pin['sha256']
    target=ROOT/'wheels'/source.name;shutil.copyfile(source,target)
    assert sha(target)==pin['sha256'];wheels.append(target)
env=json.loads((ROOT/'environment.json').read_bytes());python=ROOT/'venv/Scripts/python.exe'
for label,args in [('install',['-m','pip','install','--no-index','--no-deps',*[str(p) for p in wheels]]),
    ('pip-check',['-m','pip','check'])]:
    with (ROOT/(label+'.stdout')).open('xb') as out,(ROOT/(label+'.stderr')).open('xb') as err:
        result=subprocess.run([str(python),'-I','-B','-X','utf8',*args],env=env,cwd=ROOT,stdin=subprocess.DEVNULL,
            stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW,timeout=180)
    assert result.returncode==0,label
files=[]
for path in wheels:
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith('/') or not name.startswith(('okto_nexus/','okto_nexus_connector/','nexus_connector_core/')):continue
            digest=hashlib.sha256(archive.read(name)).hexdigest()
            assert sha(ROOT/'venv/Lib/site-packages'/name)==digest
            files.append({'path':name,'sha256':digest})
with (ROOT/'installation.json').open('x',encoding='utf-8') as out:
    json.dump({'status':'INSTALLED_OFFLINE_ONLY','wheel_sources':inputs,'files':files,'service_calls':0,'product_cli_calls':0},out,indent=2)
print(json.dumps({'installed_payloads':len(files),'installation_sha256':sha(ROOT/'installation.json')}))
