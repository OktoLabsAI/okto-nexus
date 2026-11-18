"""One finite owned installed build worker. No automatic retry."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--attempt', type=int, default=1)
args = parser.parse_args()
evidence = HERE / ('build-attempt' + str(args.attempt) + '.json')
if evidence.exists() or args.attempt < 1:
    raise RuntimeError('Never overwrite an existing attempt.')
own = Path(tempfile.mkdtemp(prefix='nexus-hst-performance-driver-')).resolve()
cwd = own / 'cwd'
cwd.mkdir()
dataset = own.parent / ('nexus-hst-performance-dataset-' + uuid.uuid4().hex)
ready_path = REPO / 'NEXUS_QUICK_CONNECT_R1/execution/qc36-final-package/READY.json'
ready = json.loads(ready_path.read_text())
env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PATHEXT'}}
system = Path(env.get('SYSTEMROOT', 'C:/Windows'))
env['PATH'] = os.pathsep.join((str(system / 'System32'), str(system), str(Path(ready['python']).parent)))
for key, relative in (('HOME', 'profile'), ('USERPROFILE', 'profile'), ('APPDATA', 'roaming'), ('LOCALAPPDATA', 'local'), ('TMP', 'temp'), ('TEMP', 'temp')):
    target = own / relative
    target.mkdir(exist_ok=True)
    env[key] = str(target)
env.update(CODEX_HOME=str(own / 'missing-codex'), CLAUDE_CONFIG_DIR=str(own / 'missing-claude'),
           PI_CODING_AGENT_DIR=str(own / 'missing-pi'))
# Worker verifies Temp ownership. Supply the OS Temp root for that lexical
# check, then it immediately replaces TMP/TEMP with its own new directories.
env['TEMP'] = env['TMP'] = tempfile.gettempdir()
command = [ready['python'], '-I', '-B', '-X', 'utf8', str(HERE / 'benchmark.py'), 'build',
    '--released', 'PACKAGE_READY', '--ready', str(ready_path), '--root', str(dataset)]
report = dict(own_driver=str(own), dataset=str(dataset), cwd=str(cwd), command=command,
    runner_sha256=hashlib.sha256((HERE / 'benchmark.py').read_bytes()).hexdigest(), state='STARTING')
(own / 'launch.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report), flush=True)
started = time.monotonic()
with (own / 'build.stdout').open('w', encoding='utf-8') as stdout, (own / 'build.stderr').open('w', encoding='utf-8') as stderr:
    child = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
    report['pid'] = child.pid
    print(json.dumps(dict(owned_pid=child.pid)), flush=True)
    try:
        report['exit_code'] = child.wait(timeout=240)
        report['state'] = 'EXITED'
    except subprocess.TimeoutExpired:
        child.terminate()
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=15)
        report.update(state='TIMEOUT_CONTAINED', exit_code=child.returncode)
report.update(seconds=time.monotonic() - started, physical_exit=child.poll() is not None)
(own / 'result.json').write_text(json.dumps(report, indent=2))
evidence.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
if report['exit_code']:
    print((own / 'build.stderr').read_text(encoding='utf-8'), flush=True)
raise SystemExit(report['exit_code'])
