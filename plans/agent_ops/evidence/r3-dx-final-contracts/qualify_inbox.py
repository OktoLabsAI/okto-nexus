from pathlib import Path
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
import zipfile

root=Path(__file__).parent
source=root/'nexus-source-v1'
out=root/'nexus-inbox-scope'
out.mkdir()
python=root/'venv/Scripts/python.exe'
wheel=next((root/'nexus-wheel-v1').glob('*.whl'))
env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP'}}
env['SystemRoot']=os.environ['SYSTEMROOT']
for name in ('USERPROFILE','APPDATA','LOCALAPPDATA'):
    env[name]=str(root/'isolated-env'/name.lower())
env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OKTO_NEXUS_NO_BANNER='1')
selected=['tests/execution_r4/test_session_read_tools.py::test_another_agent_inbox_is_denied']
proof={}
dependencies=json.loads((source/'vendor/ci/manifest.json').read_text())['artifacts']
for w,module in [(wheel,'okto_nexus'),(source/dependencies[0]['path'],'nexus_connector_core'),
                  (source/dependencies[1]['path'],'okto_nexus_connector')]:
    with zipfile.ZipFile(w) as z:
        names=[n for n in z.namelist() if n.startswith(module+'/') and not n.endswith('/')]
        for name in names:
            assert z.read(name)==(root/'venv/Lib/site-packages'/name).read_bytes(),name
            if module=='okto_nexus':assert z.read(name)==(source/'src'/name).read_bytes(),name
        proof[module]={'wheel':str(w),'sha256':hashlib.sha256(w.read_bytes()).hexdigest(),'files':len(names)}
(out/'package-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
(out/'environment.json').write_text(json.dumps({'forwarded_names':sorted(env),'personal_profile_forwarded':False,
    'provider_credentials_forwarded':False,'native_service_registration':False},indent=2)+'\n')
command=[str(python),'-I','-X','utf8',str(source/'tools/ci_installed.py'),'test','--wheel',str(wheel),
    '--output',str(out/'canonical'),'--tests',*selected]
with (out/'tests.txt').open('wb') as log:
    result=subprocess.run(command,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
cases=list(ET.parse(out/'canonical/tests.xml').iter('testcase')) if (out/'canonical/tests.xml').exists() else []
summary={'exit':result.returncode,'command':command,'cases':len(cases),
    'failures':[c.attrib for c in cases if c.find('failure') is not None or c.find('error') is not None],
    'skips':[c.attrib for c in cases if c.find('skipped') is not None]}
(out/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
with (out/'pip-check.txt').open('wb') as log:
    check=subprocess.run([str(python),'-m','pip','check'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
print(json.dumps({'exit':result.returncode,'cases':len(cases),'failures':summary['failures'],'pip_check':check.returncode}))
raise SystemExit(result.returncode or check.returncode)
