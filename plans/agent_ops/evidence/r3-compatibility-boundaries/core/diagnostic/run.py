from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent
home = root.parent/'synthetic-home'
for child in ('temp', 'appdata', 'localappdata'):
    (home/child).mkdir(exist_ok=True)
python = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ci-connector-refresh-la1tb1l6/venv/Scripts/python.exe')
env = dict(SystemRoot='C:\\Windows', WINDIR='C:\\Windows', PATH='C:\\Windows\\System32',
           COMSPEC='C:\\Windows\\System32\\cmd.exe', HOME=str(home), USERPROFILE=str(home),
           APPDATA=str(home/'appdata'), LOCALAPPDATA=str(home/'localappdata'), TEMP=str(home/'temp'),
           TMP=str(home/'temp'), USERNAME='rg06-synthetic', USERDOMAIN='rg06-synthetic',
           RG06_IMPORT_CREDENTIAL_SENTINEL='fixture-only-not-a-real-secret')
command = [shutil.which('rtk'), 'proxy', str(python), '-I', '-B', str(root/'audit.py'),
    'D:/Projetos/Techridy/okto_labs_okto_nexus/vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl',
    'D:/Projetos/Techridy/okto-nexus-connector-core/src',
    'D:/Projetos/Techridy/okto-nexus-connector-core/tools/verify_wheel.py']
assert command[0]
started = datetime.now(timezone.utc).isoformat()
process = subprocess.Popen(command, cwd=home, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
print('audit_process_pid=' + str(process.pid), flush=True)
stdout, stderr = process.communicate(timeout=60)
# The child emits keys/API names/counts only; it has no personal values to emit.
(root/'stdout.json').write_bytes(stdout)
(root/'stderr.txt').write_bytes(stderr)
report = dict(command=command, cwd=str(home), environment_inherited=False,
    synthetic_environment_keys=sorted(env), pid=process.pid, exit_code=process.returncode,
    started_at=started, ended_at=datetime.now(timezone.utc).isoformat(),
    stdout_sha256=hashlib.sha256(stdout).hexdigest(), stderr_sha256=hashlib.sha256(stderr).hexdigest(),
    script_sha256=hashlib.sha256((root/'audit.py').read_bytes()).hexdigest(), stdout_retained_verbatim=True)
(root/'invocation.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
try:
    result = json.loads(stdout)
except (ValueError, UnicodeError):
    result = dict(status='INVALID_STDOUT', stdout_bytes=len(stdout), stderr_bytes=len(stderr))
print(json.dumps(dict(exit_code=process.returncode,status=result['status'],
    imported_modules=len(result.get('imported_modules',[])), denied_events=result.get('denied_events'),
    import_failure=result.get('import_failure'), stdout_path=str(root/'stdout.json')), indent=2))
raise SystemExit(process.returncode)
