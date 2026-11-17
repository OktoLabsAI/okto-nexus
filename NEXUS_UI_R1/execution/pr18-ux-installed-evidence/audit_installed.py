from pathlib import Path
from importlib import import_module,metadata
import hashlib
import json
import os
import platform
import subprocess
import sys
import zipfile

root=Path(__file__).resolve().parent
repo=Path(r'D:\Projetos\Techridy\okto_labs_okto_nexus')
sha=lambda data:hashlib.sha256(data).hexdigest()
wheels=[(root/'artifacts/okto_nexus-0.3.5-py3-none-any.whl','okto_nexus'),(repo/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl','nexus_connector_core'),(repo/'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl','okto_nexus_connector')]
expected=['bfcd3a56cd0e901ac20de78706dc391cc0db9157ebed9c26553444b62d41b116','ea1797805279667a5b39fdb6e9e6185ed8dcb958a1c7f98e91651e841754dca5','4095484f14110b845b3481941330810f3de1d8fadf9051de0b724cb824177b90']
assert sys.flags.isolated and Path.cwd()==root
assert Path(sys.prefix).resolve()==(root/'venv').resolve()
report={'python':sys.version,'executable':sys.executable,'prefix':sys.prefix,'cwd':str(Path.cwd()),'isolated':sys.flags.isolated,'OS':platform.platform(),'sys_path':sys.path,'modules':{}}
for (wheel,module),pin in zip(wheels,expected,strict=True):
    assert sha(wheel.read_bytes())==pin
    origin=Path(import_module(module).__file__).resolve()
    assert origin.is_relative_to(Path(sys.prefix).resolve()) and 'site-packages' in str(origin)
    base=origin.parent;checked=0
    with zipfile.ZipFile(wheel) as z:
        for name in z.namelist():
            if name.startswith(module+'/') and not name.endswith('/'):
                assert (base/name.split('/',1)[1]).read_bytes()==z.read(name),name
                checked+=1
    report['modules'][module]={'origin':str(origin),'wheel':str(wheel),'wheel_sha256':pin,'payload_files_byte_equal':checked}
old=Path(r'C:\Users\jpamb\AppData\Local\Temp\nexus-ui-r1-packages-wry3ter9\nexus-release-bxp\okto_nexus-0.3.5-py3-none-any.whl')
with zipfile.ZipFile(old) as before,zipfile.ZipFile(wheels[0][0]) as after:
    nonstatic=lambda z:{name:z.read(name) for name in z.namelist() if name.startswith('okto_nexus/') and '/static/' not in name and not name.endswith('/')}
    a,b=nonstatic(before),nonstatic(after)
    assert set(a)==set(b)
    changed=[name for name in sorted(a) if a[name]!=b[name]]
    assert changed==['okto_nexus/adapters/outbound/sqlite/home.py'],changed
    counts={suffix:sum(Path(name).suffix==suffix for name in b) for suffix in ('.py','.sql')}
    counts['other']=len(b)-sum(counts.values())
    assert counts=={'.py':538,'.sql':167,'other':3},counts
    report['BXP_comparison']={'before_sha256':sha(old.read_bytes()),'nonstatic_files':len(b),'counts':counts,'changed':changed,'unchanged':len(b)-1}
    assets={name:sha(after.read(name)) for name in after.namelist() if '/static/' in name and not name.endswith('/')}
    assert any(name.endswith('/index-CKlKNFgD.js') for name in assets),assets
    assert any(name.endswith('/index-BP1to-F2.css') for name in assets),assets
    for name in assets:
        assert after.read(name)==(repo/'src'/name).read_bytes(),name
    report['assets']=assets
report['distribution_versions']={d.metadata['Name']:d.version for d in metadata.distributions()}
report['source_home_sha256']=sha((repo/'src/okto_nexus/adapters/outbound/sqlite/home.py').read_bytes())
assert report['source_home_sha256']=='e457a441560631b81f6a3cc78b299f04ead79265594d5b5b6e959577c57759c5'
report['entrypoints']={}
for name in ('okto-nexus','okto-nexus-connector'):
    argv=[str(root/'venv/Scripts'/f'{name}.exe'),'--help']
    result=subprocess.run(argv,cwd=root,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    (root/(name+'-help.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
    report['entrypoints'][name]={'argv':argv,'exit_code':result.returncode}
(root/'installed-audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','comparison':report['BXP_comparison'],'modules':report['modules'],'assets':{k:v for k,v in assets.items() if '/assets/' in k}},indent=2))
