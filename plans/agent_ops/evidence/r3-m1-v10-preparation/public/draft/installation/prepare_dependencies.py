"""Copy the already pinned dependency set into a new environment; no products."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import venv

ROOT=Path(__file__).resolve().parent
PREFIX=ROOT/'venv'
SITE=PREFIX/'Lib/site-packages'
OLD_MANIFEST=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v9-preparation-t4xaqhca/draft/installation/dependency-manifest.json')
EXPECTED_MANIFEST='6520870894d0b01e7205569816ddc6aae22b5c6e6a9474fc031fd7712d228b96'
PRODUCTS=('okto_nexus','okto_nexus_connector','nexus_connector_core')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with path.open('xb') as f:f.write((json.dumps(value,indent=2)+'\n').encode('utf-8'))

assert not PREFIX.exists() and not (ROOT/'dependency-preparation.json').exists()
assert sha(OLD_MANIFEST)==EXPECTED_MANIFEST
old=json.loads(OLD_MANIFEST.read_bytes())
SOURCE=Path(old['source'])
assert SOURCE.is_absolute()
assert {p.name for p in SOURCE.glob('*.pth')}=={'distutils-precedence.pth','pywin32.pth','_virtualenv.pth'}
assert not list(SOURCE.glob('*.egg-link')) and not list(SOURCE.glob('__editable__*'))
assert all(not name.startswith(tuple(p+'/' for p in PRODUCTS)) and not name.split('/')[0].startswith(
    ('okto_nexus-','okto_nexus_connector-','okto_nexus_connector_core-')) for name in old['files'])
assert Path(sys.base_prefix)==Path('C:/Python313')
venv.EnvBuilder(with_pip=False,system_site_packages=False).create(PREFIX)
total_bytes=0
for name,digest in old['files'].items():
    rel=Path(name)
    assert not rel.is_absolute() and '..' not in rel.parts
    source=SOURCE/rel
    assert not source.is_symlink() and sha(source)==digest
    target=SITE/rel
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    assert sha(target)==digest
    total_bytes+=target.stat().st_size
assert all(sha(SOURCE/name)==digest for name,digest in old['files'].items())
assert sha(OLD_MANIFEST)==EXPECTED_MANIFEST
environment={name:os.environ[name] for name in ('SYSTEMROOT','WINDIR','COMSPEC','PATHEXT') if name in os.environ}
environment['PATH']=os.pathsep.join([str(PREFIX/'Scripts'),str(Path(sys.base_prefix)),str(Path(os.environ['SYSTEMROOT'])/'System32')])
for var,name in [('USERPROFILE','userprofile'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata'),('TEMP','tmp'),('TMP','tmp')]:
    target=ROOT/'isolated'/name;target.mkdir(parents=True,exist_ok=True);environment[var]=str(target)
environment.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',PIP_CONFIG_FILE=os.devnull)
write(ROOT/'environment.json',environment)
manifest={'source':str(SOURCE),'destination':str(SITE),'files':old['files']}
write(ROOT/'dependency-manifest.json',manifest)
probe_code='''import importlib.util,importlib.metadata as m,json,sys
from pathlib import Path
names=('okto_nexus','okto_nexus_connector','nexus_connector_core')
assert all(importlib.util.find_spec(n) is None for n in names)
for name in ('okto-nexus','okto-nexus-connector','okto-nexus-connector-core'):
    try:m.distribution(name)
    except m.PackageNotFoundError:pass
    else:raise AssertionError('Product distribution present')
pip=importlib.util.find_spec('pip')
assert pip and Path(pip.origin).is_relative_to(Path(sys.prefix))
print(json.dumps({'prefix':sys.prefix,'python':sys.executable,'products_find_spec':{n:None for n in names},'product_dist_info_absent':True,'pip_origin':pip.origin,'pip_version':m.version('pip'),'mcp_version':m.version('mcp'),'system_site_packages':False}))
'''
with (ROOT/'dependency-probe.stdout.txt').open('xb') as out,(ROOT/'dependency-probe.stderr.txt').open('xb') as err:
    process=subprocess.Popen([str(PREFIX/'Scripts/python.exe'),'-I','-B','-X','utf8','-c',probe_code],
        cwd=ROOT/'isolated',env=environment,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    code=process.wait()
assert code==0,'Benign dependency probe failed; retain outputs'
probe=json.loads((ROOT/'dependency-probe.stdout.txt').read_bytes())
assert Path(probe['prefix'])==PREFIX
report={'status':'DEPENDENCIES_ONLY_READY','products_installed':False,'source_modified':False,
    'source_manifest':str(OLD_MANIFEST),'source_manifest_sha256':EXPECTED_MANIFEST,'source_bytes_rechecked_after':True,
    'probe':probe,'dependency_files':len(old['files']),'dependency_bytes':total_bytes,
    'dependency_manifest_sha256':sha(ROOT/'dependency-manifest.json'),'environment_sha256':sha(ROOT/'environment.json'),
    'campaign_services_or_provider_used':False,'limits':'Only pinned dependency bytes copied; product install remains absent and unauthorized.'}
write(ROOT/'dependency-preparation.json',report)
print(json.dumps(report),flush=True)
