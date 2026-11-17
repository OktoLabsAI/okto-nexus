from pathlib import Path
from importlib import import_module,metadata
import hashlib, json, os, platform, subprocess, sys, zipfile

root=Path(__file__).resolve().parent
repo=Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
sha=lambda b:hashlib.sha256(b).hexdigest()
build=json.loads((root/'final/build-manifest.json').read_text())
artifacts=[(root/'final/artifacts/okto_nexus-0.3.5-py3-none-any.whl','okto_nexus',build['artifacts']['okto_nexus-0.3.5-py3-none-any.whl']),
 (repo/'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl','nexus_connector_core','ea1797805279667a5b39fdb6e9e6185ed8dcb958a1c7f98e91651e841754dca5'),
 (repo/'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl','okto_nexus_connector','4095484f14110b845b3481941330810f3de1d8fadf9051de0b724cb824177b90')]
assert sys.flags.isolated and Path.cwd()==root
assert Path(sys.prefix).resolve()==(root/'venv').resolve()
report={'python':sys.version,'executable':sys.executable,'prefix':sys.prefix,'isolated':sys.flags.isolated,'cwd':str(Path.cwd()),'OS':platform.platform(),'sys_path':sys.path,'modules':{}}
for wheel,module,pin in artifacts:
    assert sha(wheel.read_bytes())==pin
    origin=Path(import_module(module).__file__).resolve()
    assert origin.is_relative_to(Path(sys.prefix).resolve()) and 'site-packages' in str(origin)
    checked=0
    with zipfile.ZipFile(wheel) as z:
        for name in z.namelist():
            if name.startswith(module+'/') and not name.endswith('/'):
                assert (origin.parent/name.split('/',1)[1]).read_bytes()==z.read(name),name
                if module=='okto_nexus':assert z.read(name)==(repo/'src'/name).read_bytes(),name
                checked+=1
    report['modules'][module]={'origin':str(origin),'wheel_sha256':pin,'payload_byte_equal_files':checked}
report['entrypoints']={}
for name in ('okto-nexus','okto-nexus-connector'):
    command=[str(root/'venv/Scripts'/f'{name}.exe'),'--help']
    result=subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    (root/(name+'-help.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
    report['entrypoints'][name]={'argv':command,'exit_code':result.returncode}
report['versions']={name:metadata.version(name) for name in ('okto-nexus','okto-nexus-connector-core','okto-nexus-connector')}
report['assets']=json.loads((root/'final/final-assets.json').read_text())['assets']
for name,pin in report['assets'].items():assert sha((repo/name).read_bytes())==pin
(root/'installed-audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','modules':report['modules'],'versions':report['versions']},indent=2))
