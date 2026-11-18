"""Bounded diagnostic worker after all twelve timing cuts physically exited."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import time


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--attempt', type=int, default=1)
args = parser.parse_args()
launches = list(HERE.glob('measure-*-launch.json'))
if len(launches) != 12 or not all(json.loads(p.read_text()).get('physical_exit') for p in launches):
    raise RuntimeError('Wait for all original paired timings and open complement.')
evidence = HERE / ('profile-launch.json' if args.attempt == 1 else f'profile-launch-attempt{args.attempt}.json')
if evidence.exists():
    raise RuntimeError('Never replay a diagnostic attempt without preserving its antecedent.')
own = Path(tempfile.mkdtemp(prefix='nexus-hst-performance-profile-driver-')).resolve()
(own / 'cwd').mkdir()
ready = json.loads((REPO / 'NEXUS_HOME_ESTADOS_R1/execution/package-hst/READY.json').read_text())
env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PATHEXT'}}
system = Path(env.get('SYSTEMROOT', 'C:/Windows'))
env.update(PATH=os.pathsep.join((str(system / 'System32'), str(system), str(Path(ready['python']).parent))),
           HOME=str(own), USERPROFILE=str(own), APPDATA=str(own), LOCALAPPDATA=str(own),
           TMP=tempfile.gettempdir(), TEMP=tempfile.gettempdir())
command = [ready['python'], '-I', '-B', '-X', 'utf8', str(HERE / 'profile-worker.py')]
report = dict(command=command, own_driver=str(own), state='STARTING')
print(json.dumps(report), flush=True)
started = time.monotonic()
with (own / 'profile.stdout').open('w', encoding='utf-8') as stdout, (own / 'profile.stderr').open('w', encoding='utf-8') as stderr:
    child = subprocess.Popen(command, cwd=own / 'cwd', env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
    report['pid'] = child.pid
    print(json.dumps(dict(owned_pid=child.pid)), flush=True)
    try:
        report['exit_code'] = child.wait(timeout=180)
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
print((own / ('profile.stderr' if report['exit_code'] else 'profile.stdout')).read_text(encoding='utf-8'), flush=True)
raise SystemExit(report['exit_code'])
