from pathlib import Path
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET

root=Path(__file__).parent
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
python=Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv/Scripts/python.exe')
test=repo/'tests/execution_r4/test_two_existing_mcp_clients.py'
helper=repo/'tests/execution_r4/test_service_restart_contracts.py'
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (test,helper)}
assert before[str(test)]=='1b8bee3d7601bcf7d9b7793af521cfd13e7a4f69ae8bb946943ad15b80c5429c'
selectors=dict(NEXUS_AC03_NODE='C:/Program Files/nodejs/node.exe',
    NEXUS_AC03_INSPECTOR_ROOT='C:/Users/jpamb/AppData/Local/npm-cache/_npx/5a9d879542beca3a/node_modules/@modelcontextprotocol/inspector',
    NEXUS_AC03_PYTHON='C:/Python313/python.exe',
    NEXUS_AC03_PYTHON_PATHS=json.dumps(['C:/Users/jpamb/AppData/Roaming/Python/Python313/site-packages']))
(root/'selectors.json').write_text(json.dumps(selectors,indent=2)+'\n',encoding='utf-8')
home=root/'source-home'
home.mkdir(exist_ok=True)
env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC'}}
env.update(PATH='C:/Windows/System32',HOME=str(home),USERPROFILE=str(home),APPDATA=str(home),
    LOCALAPPDATA=str(home),TEMP=str(home),TMP=str(home),PYTHONDONTWRITEBYTECODE='1',
    PYTHONIOENCODING='utf-8',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',**selectors)
launcher=root/'source-launcher.py'
launcher.write_text('import sys\n'+f'sys.path[:0]={[str(repo/"src"),str(repo/"tests"),str(repo/"tests/execution_r4")]!r}\n'
    +'import pytest\nraise SystemExit(pytest.main(sys.argv[1:]))\n',encoding='utf-8')
out=root/'source-final'
out.mkdir()
cmd=[str(python),'-I','-X','utf8',str(launcher),str(test),'-q','-p','pytest_asyncio.plugin',
    '--basetemp',str(out/'runtime'),'--junitxml',str(out/'tests.xml')]
with (out/'stdout.log').open('w',encoding='utf-8') as log:
    process=subprocess.Popen(cmd,cwd=repo,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
    print(json.dumps(dict(pid=process.pid,output=str(out),selectors=str(root/'selectors.json'))),flush=True)
    code=process.wait()
after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (test,helper)}
cases=list(ET.parse(out/'tests.xml').iter('testcase')) if (out/'tests.xml').exists() else []
result=dict(returncode=code,source_hashes_before=before,source_hashes_after=after,inputs_unchanged=before==after,
    cases=[dict(node=c.get('classname','')+'::'+c.get('name',''),status=next((x for x in ('error','failure','skipped') if c.find(x) is not None),'passed')) for c in cases])
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
