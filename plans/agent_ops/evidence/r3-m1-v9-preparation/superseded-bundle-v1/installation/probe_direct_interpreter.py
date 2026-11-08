"""Benign own Python identity/prefix proof only. No timeout kill or product."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).parent
PREFIX = ROOT / 'venv'
PYTHON = PREFIX / 'Scripts/python.exe'
BASE = Path('C:/Python313/python.exe')
environment = json.loads((ROOT / 'environment.json').read_text())
environment['__PYVENV_LAUNCHER__'] = str(PYTHON)
code = '''import importlib.util,json,os,sys
from pathlib import Path
import pip
names=('okto_nexus','okto_nexus_connector','nexus_connector_core')
assert all(importlib.util.find_spec(n) is None for n in names)
print(json.dumps({'prefix':sys.prefix,'python':sys.executable,'pid':os.getpid(),
                  'pip_origin':pip.__file__,'products_absent':True}),flush=True)
'''
with (ROOT / 'direct-interpreter-final.stdout.txt').open('xb') as out, (ROOT / 'direct-interpreter-final.stderr.txt').open('xb') as err:
    process = subprocess.Popen([str(BASE), '-I', '-B', '-X', 'utf8', '-c', code],
        cwd=ROOT / 'isolated', env=environment, stdout=out, stderr=err,
        creationflags=subprocess.CREATE_NO_WINDOW)
    # Own real base-Python handle retained and waited; no timer kills it.
    result_code = process.wait()
metadata = json.loads((ROOT / 'direct-interpreter-final.stdout.txt').read_text())
assert result_code == 0
assert metadata['pid'] == process.pid
assert Path(metadata['prefix']) == PREFIX
assert Path(metadata['python']) == PYTHON
assert Path(metadata['pip_origin']).is_relative_to(PREFIX)
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
result = {'status':'PASS', 'scope':'Benign own Python metadata only; no product install/import',
          'metadata':metadata, 'launcher_pid_matches_child':True,
          'observed_pid':process.pid, 'returncode':result_code,
          'base_executable':str(BASE), 'base_executable_sha256':sha(BASE),
          'venv_python_sha256':sha(PYTHON),
          'requirements_sha256':sha(ROOT / 'products-requirements.txt')}
(ROOT / 'direct-interpreter-final.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
