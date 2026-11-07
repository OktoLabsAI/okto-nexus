import hashlib
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
profile = root/'isolated-profile'
profile.mkdir(exist_ok=True)
environment = {k: v for k, v in os.environ.items()
               if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP'}}
environment.update(USERPROFILE=str(profile), APPDATA=str(profile), LOCALAPPDATA=str(profile),
                   PATH=str(Path(os.environ.get('SYSTEMROOT','C:/Windows'))/'System32'),
                   PYTHONIOENCODING='utf-8', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
                   OKTO_NEXUS_NO_BANNER='1')
os.environ.clear()
os.environ.update(environment)
workspace = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
sources = [workspace/'src', Path('D:/Projetos/Techridy/okto-nexus-connector/src'),
           Path('D:/Projetos/Techridy/okto-nexus-connector-core/src')]
sys.path[:0] = [str(p) for p in sources] + [str(workspace/'tests'),str(workspace/'tests/execution_r4')]
import pytest
import okto_nexus
import okto_nexus_connector
import nexus_connector_core
packages = (okto_nexus, okto_nexus_connector, nexus_connector_core)
for module, source in zip(packages,sources):
    assert Path(module.__file__).resolve().is_relative_to(source.resolve())
test = workspace/'tests/execution_r4/test_service_surviving_child.py'
helper = workspace/'tests/execution_r4/test_service_restart_contracts.py'
report = root/(sys.argv[1] if len(sys.argv)>1 else 'initial.xml')
command = ['-c',str(root/'pytest.ini'),'-p','pytest_asyncio.plugin','--rootdir='+str(workspace),
           '--confcutdir='+str(workspace/'tests/execution_r4'),str(test),'-q','--tb=short',
           '--junitxml='+str(report),'--basetemp='+str(root/(report.stem+'-private'))]
proof = {'mode':'source','command':command,'imports':{m.__name__:m.__file__ for m in packages},
         'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (test,helper)},
         'providers':False,'personal_services':False,'os_task_registration':False}
(root/(report.stem+'-command.json')).write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
code = pytest.main(command)
proof['exit_code'] = int(code)
proof['unchanged'] = all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in proof['inputs'].items())
assert proof['unchanged']
(root/(report.stem+'-result.json')).write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
raise SystemExit(code)
