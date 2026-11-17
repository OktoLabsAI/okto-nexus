"""Required new open-workload build, after all original paired cuts exit."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for n in (1, 10, 100):
    for variant in ('baseline-v1', 'candidate-v1', 'candidate-v2'):
        previous = json.loads((HERE / f'measure-{n}-{variant}-launch.json').read_text())
        if not previous.get('physical_exit'):
            raise RuntimeError('Original paired cut is not physically exited.')
evidence = HERE / 'build-open-attempt1.json'
if evidence.exists():
    raise RuntimeError('Do not overwrite/replay an open workload build.')
own = Path(tempfile.mkdtemp(prefix='nexus-hst-performance-open-driver-')).resolve()
(own / 'cwd').mkdir()
root = own.parent / ('nexus-hst-performance-open-' + uuid.uuid4().hex)
ready_path = REPO / 'NEXUS_QUICK_CONNECT_R1/execution/qc36-final-package/READY.json'
ready = json.loads(ready_path.read_text())
env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PATHEXT'}}
system = Path(env.get('SYSTEMROOT', 'C:/Windows'))
env['PATH'] = os.pathsep.join((str(system / 'System32'), str(system), str(Path(ready['python']).parent)))
for key, relative in (('HOME', 'profile'), ('USERPROFILE', 'profile'), ('APPDATA', 'roaming'), ('LOCALAPPDATA', 'local')):
    target = own / relative
    target.mkdir(exist_ok=True)
    env[key] = str(target)
env.update(TMP=tempfile.gettempdir(), TEMP=tempfile.gettempdir(), CODEX_HOME=str(own / 'missing-codex'),
           CLAUDE_CONFIG_DIR=str(own / 'missing-claude'), PI_CODING_AGENT_DIR=str(own / 'missing-pi'))
command = [ready['python'], '-I', '-B', '-X', 'utf8', str(HERE / 'build-open-worker.py'),
           '--released', 'PACKAGE_READY', '--ready', str(ready_path), '--root', str(root)]
report = dict(own_driver=str(own), dataset=str(root), command=command, state='STARTING')
print(json.dumps(report), flush=True)
started = time.monotonic()
with (own / 'build.stdout').open('w', encoding='utf-8') as stdout, (own / 'build.stderr').open('w', encoding='utf-8') as stderr:
    child = subprocess.Popen(command, cwd=own / 'cwd', env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
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
evidence.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
print((own / ('build.stderr' if report['exit_code'] else 'build.stdout')).read_text(encoding='utf-8'), flush=True)
raise SystemExit(report['exit_code'])
