"""One hidden-console pytest, fail-closed input/signal ownership, finite cleanup."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / 'qc22-owned-console-interrupt'))
from win import Owned, kernel, same_image

ROOT = Path(json.loads((HERE / 'allocation.json').read_text())['root']).resolve()
PACKAGE = Path(json.loads((HERE.parent / 'qc11-package/allocation.json').read_text())['root']).resolve()
PYTHON = PACKAGE / 'venv/Scripts/python.exe'
assert Path(sys.prefix).resolve() == PYTHON.parent.parent.resolve()
assert os.name == 'nt' and not (ROOT / 'result.json').exists()
rtk = shutil.which('rtk')
assert rtk
allowed_images = [str(PYTHON.resolve()), str(Path(sys._base_executable).resolve())]
spec = importlib.util.spec_from_file_location('qc37_environment', HERE.parent / 'qc08-package/package.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
(ROOT / 'environment').mkdir(exist_ok=True)
env = builder.environment(ROOT / 'environment')
env.update(PATH=str(ROOT / 'empty-path'), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
    OKTO_NEXUS_NO_BANNER='1')
assert not Path(env['TMP']).resolve().is_relative_to(ROOT / 'cwd')


def payload():
    values = {}
    for module, wheel in (('okto_nexus', PACKAGE / 'artifacts/okto_nexus-0.3.6-py3-none-any.whl'),
        ('nexus_connector_core', REPO / 'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'),
        ('okto_nexus_connector', REPO / 'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl')):
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if name.startswith(module + '/') and not name.endswith('/'):
                    value = (PACKAGE / 'venv/Lib/site-packages' / name).read_bytes()
                    assert value == archive.read(name), name
                    values[name] = hashlib.sha256(value).hexdigest()
    return values


known = {}
observed = []


def track(process, script):
    owner = Owned(process.pid)
    assert any(same_image(owner.image, image) for image in allowed_images)
    known[process.pid] = (owner, str(script))


def discover():
    live = [pid for pid, (owner, _) in known.items() if owner.alive()]
    if not live:
        return
    query = ' OR '.join('ParentProcessId=' + str(pid) for pid in live)
    command = 'Get-CimInstance Win32_Process -Filter "' + query + '" | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | ConvertTo-Json'
    result = subprocess.run([rtk, 'proxy', 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe',
        '-NoProfile', '-Command', command], cwd=ROOT / 'cwd', env=env, capture_output=True, text=True, timeout=8)
    assert result.returncode == 0
    rows = json.loads(result.stdout) if result.stdout.strip() else []
    for row in rows if isinstance(rows, list) else [rows]:
        pid, parent = row['ProcessId'], row['ParentProcessId']
        if pid in known or parent not in known or not known[parent][0].alive():
            continue
        expected = known[parent][1]
        if expected not in (row.get('CommandLine') or ''):
            observed.append(dict(pid=pid, parent_pid=parent, image=row.get('ExecutablePath'), authorization='not a console client; not included in signal/termination permit'))
            continue
        try:
            owner = Owned(pid, parent)
        except ProcessLookupError:
            continue
        assert any(same_image(owner.image, image) for image in allowed_images)
        known[pid] = (owner, expected)


before = payload()
assert len(before) == 1027
processes, logs, commands, forced = [], [], [], []
started = time.monotonic()
failure = None
try:
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    log = (ROOT / 'child.log').open('wb')
    logs.append(log)
    argv = [str(PYTHON), '-I', '-B', str(ROOT / 'child.py')]
    child = subprocess.Popen(argv, cwd=ROOT / 'cwd', env=env, stdout=log, stderr=subprocess.STDOUT,
        startupinfo=startup, creationflags=subprocess.CREATE_NEW_CONSOLE)
    processes.append(child)
    commands.append(dict(kind='single_pytest_child', argv=argv, creationflags='CREATE_NEW_CONSOLE', show_window='SW_HIDE'))
    track(child, ROOT / 'child.py')
    while not (ROOT / 'child-ready.json').exists():
        discover()
        assert child.poll() is None, 'Child exited without real-console readiness'
        assert time.monotonic() - started < 45, 'No child console readiness'
        time.sleep(.1)
    ready = json.loads((ROOT / 'child-ready.json').read_text())
    discover()
    assert ready['stdin_isatty'] is True and not ready['window']['visible']
    assert ready['pid'] in known and set(ready['console_members']) <= set(known)
    assert ready['original_test_sha256'] == json.loads((HERE / 'mechanism.json').read_text())['original_test_sha256']
    print(json.dumps(dict(stage='owned_hidden_console_ready', members=ready['console_members'], pid=ready['pid'])), flush=True)
    log = (ROOT / 'controller.log').open('wb')
    logs.append(log)
    argv = [str(PYTHON), '-I', '-B', str(ROOT / 'controller.py')]
    control = subprocess.Popen(argv, cwd=ROOT / 'cwd', env=env, stdin=subprocess.DEVNULL,
        stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    processes.append(control)
    commands.append(dict(kind='isolated_controller', argv=argv, creationflags='CREATE_NO_WINDOW'))
    track(control, ROOT / 'controller.py')
    while not (ROOT / 'controller-started.json').exists():
        discover()
        assert control.poll() is None and time.monotonic() - started < 60
        time.sleep(.1)
    controller = json.loads((ROOT / 'controller-started.json').read_text())
    discover()
    assert controller['pid'] in known
    permit = dict(child_main_pid=ready['pid'], controller_main_pid=controller['pid'], console_window=ready['window'],
        owned_processes=[owner.facts() for owner, _ in known.values()])
    (ROOT / 'permit.json').write_text(json.dumps(permit, indent=2))
    last_stage = None
    while any(process.poll() is None for process in processes):
        discover()
        assert time.monotonic() - started < 180, 'Owned-console cut deadline'
        if (ROOT / 'controller-refused.json').exists():
            raise RuntimeError('Controller refused; no extra input or signal may be attempted')
        stage = 'ctrl_c_attempt_recorded' if (ROOT / 'signal-intent.json').exists() else 'y_input_recorded' if (ROOT / 'input-result.json').exists() else 'waiting_exact_review_prompt'
        if stage != last_stage:
            print(json.dumps(dict(stage=stage)), flush=True)
            last_stage = stage
        time.sleep(.1)
    assert child.returncode == control.returncode == 0, 'Test/controller did not both exit zero'
    assert json.loads((ROOT / 'child-result.json').read_text())['pytest_exit'] == 0
    assert json.loads((ROOT / 'controller-result.json').read_text())['status'] == 'RESIZE_AND_ONE_TEST_RESUME_CONFIRMED'
except BaseException as error:
    failure = dict(error=type(error).__name__, reason=str(error))
finally:
    discover()
    for owner, script in reversed(list(known.values())):
        if owner.alive():
            assert any(same_image(owner.image, image) for image in allowed_images)
            assert script in (str(ROOT / 'child.py'), str(ROOT / 'controller.py'))
            forced.append(owner.facts())
            assert kernel.TerminateProcess(owner.handle, 124)
    for process in processes:
        process.wait(timeout=10)
    deadline = time.monotonic() + 10
    while any(owner.alive() for owner, _ in known.values()) and time.monotonic() < deadline:
        time.sleep(.05)
    after_processes = [owner.facts() for owner, _ in known.values()]
    assert all(not value['alive'] for value in after_processes)
    for owner, _ in known.values():
        owner.close()
    for log in logs:
        log.close()
after = payload()
assert before == after
pins = json.loads((ROOT / 'source-pins.json').read_text())
drift = [name for name, pin in pins.items() if hashlib.sha256((REPO / name).read_bytes()).hexdigest() != pin]
assert not drift, drift
report = dict(at=datetime.now(timezone.utc).isoformat(), status='PASS' if failure is None else 'NOT_QUALIFIED',
    failure=failure, commands=commands, own_root=str(ROOT), process_proofs=after_processes,
    observed_non_clients=observed, containment=forced, elapsed_seconds=time.monotonic() - started,
    payload_files=1027, payload_drift=[], source_drift=[], provider_calls=0)
(ROOT / 'result.json').write_text(json.dumps(report, indent=2))
print(json.dumps(dict(status=report['status'], failure=failure, containment_count=len(forced),
    all_owned_processes_exited=True, payload_drift=[])), flush=True)
raise SystemExit(0 if failure is None else 2)
