"""Write fixed wheel requirements and probe only the prepared interpreter."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('timed_install', ROOT / 'timed_install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
requirements = ''.join(Path(pin['wheel']).as_uri() + ' --hash=sha256:' + pin['sha256'] + '\n'
                       for pin in installer.WHEELS.values())
with installer.REQUIREMENTS.open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(requirements)
environment = json.loads((ROOT / 'environment.json').read_text(encoding='utf-8'))
environment['__PYVENV_LAUNCHER__'] = str(installer.PYTHON)
code = '''import importlib.util, json, os, sys
print(json.dumps({'prefix': sys.prefix, 'python': sys.executable,
 'pid': os.getpid(), 'pip_origin': importlib.util.find_spec('pip').origin,
 'products_absent': all(importlib.util.find_spec(n) is None for n in
 ('okto_nexus', 'okto_nexus_connector', 'nexus_connector_core'))}))
'''
process = subprocess.Popen([str(installer.BASE_PYTHON), '-I', '-B', '-X', 'utf8', '-c', code],
    cwd=ROOT / 'isolated', env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
stdout, stderr = process.communicate(timeout=30)
(ROOT / 'direct-interpreter-final.stdout.txt').write_bytes(stdout)
(ROOT / 'direct-interpreter-final.stderr.txt').write_bytes(stderr)
assert process.returncode == 0 and not stderr
metadata = json.loads(stdout)
assert metadata['pid'] == process.pid
assert Path(metadata['prefix']) == installer.PREFIX
assert Path(metadata['python']) == installer.PYTHON
assert metadata['products_absent'] is True
assert Path(metadata['pip_origin']).is_relative_to(installer.PREFIX)
sha = lambda raw: hashlib.sha256(raw).hexdigest()
report = {'status': 'PASS', 'scope': 'Benign interpreter metadata only; no product install',
          'metadata': metadata, 'launcher_pid_matches_child': True, 'observed_pid': process.pid,
          'returncode': process.returncode,
          'base_executable': str(installer.BASE_PYTHON),
          'base_executable_sha256': sha(installer.BASE_PYTHON.read_bytes()),
          'venv_python_sha256': sha(installer.PYTHON.read_bytes()),
          'requirements_sha256': sha(installer.REQUIREMENTS.read_bytes())}
(ROOT / 'direct-interpreter-final.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
installer.verify_dependencies()
installer.verify_wheels()
print(json.dumps(report))
