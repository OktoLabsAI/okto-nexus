"""Offline own-venv installation of immutable final wheels; no services."""
from pathlib import Path
import hashlib,json,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parent
SOURCE=Path('C:/Users/jpamb/AppData/Local/Temp/r3-native-t19-t20-v2-fk9g74yv/final-build/wheels')
PINS={'okto_nexus-0.3.3-py3-none-any.whl':'d67365a6a407b12671412f4501f156cbdb8c5d6d196cf5679352e6c4ffe8dbb0',
 'okto_nexus_connector_core-0.0.14-py3-none-any.whl':'d881ab35ac619147df51cbe3a10964e534c50acd117e45e2612dcec7fbc1afe9',
 'okto_nexus_connector-0.0.12-py3-none-any.whl':'06f711467fa43af5996b5e2bf5e2a01e410a431d9013ccac318200b8902e7275'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
(ROOT/'wheels').mkdir()
for name,digest in PINS.items():
    assert sha(SOURCE/name)==digest;shutil.copyfile(SOURCE/name,ROOT/'wheels'/name)
    assert sha(ROOT/'wheels'/name)==digest
env=json.loads((ROOT/'environment.json').read_bytes());python=ROOT/'venv/Scripts/python.exe'
for label,args in [('install',['-m','pip','install','--no-index','--no-deps',*[str(ROOT/'wheels'/n) for n in PINS]]),
    ('pip-check',['-m','pip','check'])]:
    with (ROOT/(label+'.stdout')).open('xb') as out,(ROOT/(label+'.stderr')).open('xb') as err:
        result=subprocess.run([str(python),'-I','-B','-X','utf8',*args],env=env,cwd=ROOT,
            stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW,timeout=180)
    assert result.returncode==0,label
payloads=[]
for name in PINS:
    with zipfile.ZipFile(ROOT/'wheels'/name) as wheel:
        for item in wheel.namelist():
            if item.endswith('/') or not item.startswith(('okto_nexus/','okto_nexus_connector/','nexus_connector_core/')):continue
            digest=hashlib.sha256(wheel.read(item)).hexdigest();path=ROOT/'venv/Lib/site-packages'/item
            assert sha(path)==digest;payloads.append({'path':item,'sha256':digest})
with (ROOT/'installation.json').open('x',encoding='utf-8') as out:
    json.dump({'status':'INSTALLED_OFFLINE_ONLY','wheels':PINS,'files':payloads,'model_turns':0,'service_calls':0},out,indent=2)
print(json.dumps({'installed_payloads':len(payloads),'installation_sha256':sha(ROOT/'installation.json')}))
