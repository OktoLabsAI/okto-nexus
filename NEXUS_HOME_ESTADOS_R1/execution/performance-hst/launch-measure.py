"""One sequenced own measurement worker per dataset/variant; no retry."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
parser = argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument('--connections', type=int, choices=(1, 10, 100), required=True)
parser.add_argument('--variant', choices=('baseline-v1', 'candidate-v1', 'candidate-v2'), required=True)
parser.add_argument('--workload', choices=('mixed', 'open'), default='mixed')
args = parser.parse_args()
build = json.loads((HERE / ('build-open-attempt1.json' if args.workload == 'open' else 'build-attempt3.json')).read_text())
assert build['exit_code'] == 0 and build['physical_exit']
own = Path(build['own_driver'])
dataset = Path(build['dataset'])
ready_path = REPO / ('NEXUS_QUICK_CONNECT_R1/execution/qc36-final-package/READY.json'
    if args.variant == 'baseline-v1' else 'NEXUS_HOME_ESTADOS_R1/execution/package-hst/READY.json')
ready = json.loads(ready_path.read_text())
name = f'measure-{args.connections}-{args.variant}' if args.workload == 'mixed' else f'measure-open-{args.connections}-{args.variant}'
evidence = HERE / (name + '-launch.json')
output = dataset / 'reports' / (name + '.json')
if evidence.exists() or output.exists():
    raise RuntimeError('Never overwrite or replay a measurement clone.')
env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PATHEXT'}}
system = Path(env.get('SYSTEMROOT', 'C:/Windows'))
env['PATH'] = os.pathsep.join((str(system / 'System32'), str(system), str(Path(ready['python']).parent)))
for key, relative in (('HOME', 'profile'), ('USERPROFILE', 'profile'), ('APPDATA', 'roaming'), ('LOCALAPPDATA', 'local')):
    env[key] = str(own / relative)
env.update(TMP=tempfile.gettempdir(), TEMP=tempfile.gettempdir(), CODEX_HOME=str(own / 'missing-codex'),
           CLAUDE_CONFIG_DIR=str(own / 'missing-claude'), PI_CODING_AGENT_DIR=str(own / 'missing-pi'))
command = [ready['python'], '-I', '-B', '-X', 'utf8', str(HERE / 'measure-worker.py'), 'measure',
    '--released', 'PACKAGE_READY', '--ready', str(ready_path), '--dataset', str(dataset / 'dataset.json'),
    '--connections', str(args.connections), '--variant', args.variant, '--output', str(output)]
report = dict(name=name, command=command, own_driver=str(own), output=str(output), state='STARTING')
print(json.dumps(report), flush=True)
started = time.monotonic()
with (own / (name + '.stdout')).open('w', encoding='utf-8') as stdout, (own / (name + '.stderr')).open('w', encoding='utf-8') as stderr:
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
if report['exit_code']:
    print((own / (name + '.stderr')).read_text(encoding='utf-8'), flush=True)
elif output.exists():
    result = json.loads(output.read_text())
    print(json.dumps(dict(status=result['status'], targets=result['targets'],
        series={k: {'p50': v['p50_ms'], 'p95': v['nearest_rank_p95_ms'], 'count': v['count']} for k, v in result['series'].items()})), flush=True)
raise SystemExit(report['exit_code'])
