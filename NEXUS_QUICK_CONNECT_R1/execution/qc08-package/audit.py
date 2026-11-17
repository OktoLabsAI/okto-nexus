"""Installed -I payload and no-effect entrypoint audit, outside the checkout."""
import hashlib
import importlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
root=Path(json.loads((HERE/'allocation.json').read_text())['root']).resolve()
assert sys.flags.isolated and Path.cwd().resolve()==root
assert Path(sys.prefix).resolve()==(root/'venv').resolve()
def sha(value):
    return hashlib.sha256(value).hexdigest()
rtk=shutil.which('rtk')
assert rtk
nexus=root/'artifacts/okto_nexus-0.3.6-py3-none-any.whl'
build=json.loads((root/'build-manifest.json').read_text())
artifacts=[(nexus,'okto_nexus',build['artifacts'][nexus.name]),
    (REPO/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl','nexus_connector_core',
     'ea1797805279667a5b39fdb6e9e6185ed8dcb958a1c7f98e91651e841754dca5'),
    (REPO/'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl','okto_nexus_connector',
     '4095484f14110b845b3481941330810f3de1d8fadf9051de0b724cb824177b90')]
report=dict(python=sys.version,executable=sys.executable,prefix=sys.prefix,isolated=True,
    cwd=str(Path.cwd()),OS=platform.platform(),sys_path=sys.path,modules={},commands=[])
payload={}
for wheel,module,pin in artifacts:
    assert sha(wheel.read_bytes())==pin
    origin=Path(importlib.import_module(module).__file__).resolve()
    assert origin.is_relative_to(Path(sys.prefix).resolve()) and 'site-packages' in str(origin)
    files={}
    with zipfile.ZipFile(wheel) as archive:
        forbidden=[name for name in archive.namelist() if name.lower().endswith(('.db','.sqlite','.sqlite3','.env'))]
        assert not forbidden,forbidden
        for name in archive.namelist():
            if not name.startswith(module+'/') or name.endswith('/'):
                continue
            data=archive.read(name)
            assert (origin.parent/name.split('/',1)[1]).read_bytes()==data,name
            if module=='okto_nexus':
                assert (REPO/'src'/name).read_bytes()==data,name
                assert (root/'source/src'/name).read_bytes()==data,name
            files[name]=sha(data)
    payload[module]=files
    report['modules'][module]=dict(origin=str(origin),wheel_sha256=pin,payload_files=len(files),
        equal_installed_wheel=True,equal_checkout_source=module=='okto_nexus')

sdist=root/'artifacts/okto_nexus-0.3.6.tar.gz'
with tarfile.open(sdist,'r:gz') as archive:
    top=archive.getmembers()[0].name.split('/')[0]
    for name,pin in payload['okto_nexus'].items():
        data=archive.extractfile(top+'/src/'+name).read()
        assert sha(data)==pin,name
report['sdist']=dict(sha256=sha(sdist.read_bytes()),module_files_equal_wheel=len(payload['okto_nexus']))
report['assets']={name:pin for name,pin in payload['okto_nexus'].items() if '/http/static/' in name}
assert any(name.endswith('index-CfDr8rCI.js') for name in report['assets'])

# Metadata-only CLI paths run with no external executable search or real home.
env={key:os.environ[key] for key in os.environ if key.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT'}}
env.update(PATH='',USERPROFILE=str(root/'userprofile'),HOME=str(root/'userprofile'),
    APPDATA=str(root/'appdata'),LOCALAPPDATA=str(root/'localappdata'),TEMP=str(root/'tmp'),TMP=str(root/'tmp'),
    PYTHONUTF8='1',PIP_CONFIG_FILE=os.devnull)
for label,argv,expected in [
    ('nexus-help',[root/'venv/Scripts/okto-nexus.exe','--help'],0),
    ('connector-help',[root/'venv/Scripts/okto-nexus-connector.exe','--help'],0),
    ('codex-help',[root/'venv/Scripts/okto-nexus.exe','codex','--help'],0),
    ('claude-help',[root/'venv/Scripts/okto-nexus.exe','claude','--help'],0),
    ('pi-help',[root/'venv/Scripts/okto-nexus.exe','pi','--help'],0),
    ('badflag-json',[root/'venv/Scripts/okto-nexus.exe','connect','codex','--qc08-unknown-flag','--json'],2),
]:
    command=[rtk,'proxy',*map(str,argv)]
    result=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=30)
    (root/(label+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
    report['commands'].append(dict(label=label,argv=command,exit_code=result.returncode,expected=expected))
    assert result.returncode==expected,(label,result.returncode,result.stderr)
    if label=='badflag-json':
        value=json.loads(result.stdout)
        report['badflag_json']=value
        assert value.get('state')=='refused' and value.get('code')=='INVALID_ARGUMENTS',value
        assert value.get('effects_started') is False and value.get('lifecycle_requested') is False,value
report['versions']={name:metadata.version(name) for name in ('okto-nexus','okto-nexus-connector-core','okto-nexus-connector')}
(root/'payload-manifest.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
(root/'installed-audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status='PASS',modules=report['modules'],versions=report['versions'])))
