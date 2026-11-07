from pathlib import Path
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET

root=Path(__file__).parent
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
python=Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv/Scripts/python.exe')
selected=['tests/execution_r4/test_two_existing_mcp_clients.py','tests/execution_r4/test_two_existing_mcp_cooperation.py']
source_inputs=selected+['tests/execution_r4/test_service_restart_contracts.py',
    'src/okto_nexus/application/terminal_cooperation.py','src/okto_nexus/application/terminal_coordination.py',
    'src/okto_nexus/adapters/outbound/cooperation_files.py','src/okto_nexus/adapters/outbound/coordination_files.py',
    'src/okto_nexus/application/handoff.py']
before={name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in source_inputs}
assert before[selected[0]]=='fb32d2ec1e4e4208bc0a33cb9128ed12cec5aa6577ff72038be90dd3b32b9812'
assert before[selected[1]]=='7579bf180d521a2d1d2fa1d70cbbe95dcc0385b4c00303f1c9d15f1923a0bf1b'
prior=Path('C:/Users/jpamb/AppData/Local/Temp/ac03-client-capabilities-03khbbtj/public-final')
selectors=json.loads((prior/'selectors.json').read_text())
modules=json.loads((prior/'local-capabilities.json').read_text())['inputs']
assert all(hashlib.sha256(Path(x['path']).read_bytes()).hexdigest()==x['sha256'] for x in modules)
(root/'selectors.json').write_text(json.dumps(selectors,indent=2)+'\n',encoding='utf-8')
(root/'distributed-module-inputs.json').write_text(json.dumps(modules,indent=2)+'\n',encoding='utf-8')
home=root/'source-home'
home.mkdir(exist_ok=True)
env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC'}}
env.update(PATH='C:/Windows/System32',HOME=str(home),USERPROFILE=str(home),APPDATA=str(home),
    LOCALAPPDATA=str(home),TEMP=str(home),TMP=str(home),PYTHONDONTWRITEBYTECODE='1',
    PYTHONIOENCODING='utf-8',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',**selectors)
launcher=root/'source-launcher.py'
launcher.write_text('import sys\n'+f'sys.path[:0]={[str(repo/"src"),str(repo/"tests"),str(repo/"tests/execution_r4")]!r}\n'
    +'import pytest\nraise SystemExit(pytest.main(sys.argv[1:]))\n',encoding='utf-8')
out=root/'source-initial'
out.mkdir()
cmd=[str(python),'-I','-X','utf8',str(launcher),*[str(repo/name) for name in selected],'-q','-p','pytest_asyncio.plugin',
    '--basetemp',str(out/'runtime'),'--junitxml',str(out/'tests.xml')]
with (out/'stdout.log').open('w',encoding='utf-8') as log:
    process=subprocess.Popen(cmd,cwd=repo,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
    print(json.dumps(dict(pid=process.pid,output=str(out),selectors=str(root/'selectors.json'))),flush=True)
    code=process.wait()
after={name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in source_inputs}
module_changes=[x['path'] for x in modules if hashlib.sha256(Path(x['path']).read_bytes()).hexdigest()!=x['sha256']]
cases=list(ET.parse(out/'tests.xml').iter('testcase')) if (out/'tests.xml').exists() else []
result=dict(returncode=code,source_hashes_before=before,source_hashes_after=after,inputs_unchanged=before==after,
    distributed_module_changes=module_changes,
    cases=[dict(node=c.get('classname','')+'::'+c.get('name',''),seconds=c.get('time'),
        status=next((x for x in ('error','failure','skipped') if c.find(x) is not None),'passed')) for c in cases])
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
