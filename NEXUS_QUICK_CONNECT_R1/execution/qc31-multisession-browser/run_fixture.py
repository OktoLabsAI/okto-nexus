"""Finite supervisor of one own canonical protocol/browser fixture."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import zipfile

import psutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
allocation = json.loads((HERE / 'allocation.json').read_text())
ROOT = Path(allocation['root'])
PREFIX = Path(allocation['prefix'])
spec = importlib.util.spec_from_file_location('qc31_env', HERE.parent / 'qc11-package/package.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
env = builder.environment(ROOT)
env.update(PATH='', CODEX_HOME=str(ROOT / 'os-home/.codex'), CLAUDE_CONFIG_DIR=str(ROOT / 'os-home/.claude'))
for name in ('CODEX_HOME', 'CLAUDE_CONFIG_DIR'):
    Path(env[name]).mkdir(exist_ok=True)


def payload():
    values = {}
    wheels = [PREFIX.parent / 'artifacts/okto_nexus-0.3.6-py3-none-any.whl',
              REPO / 'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl',
              REPO / 'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl']
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if name.startswith(('okto_nexus/', 'nexus_connector_core/', 'okto_nexus_connector/')) and not name.endswith('/'):
                    data = (PREFIX / 'Lib/site-packages' / name).read_bytes()
                    assert data == archive.read(name), name
                    values[name] = hashlib.sha256(data).hexdigest()
    assert len(values) == 1027
    return values


before = payload()
(ROOT / 'payload-before.json').write_text(json.dumps(before, indent=2) + '\n')
source = builder.pins()
(ROOT / 'source-before.json').write_text(json.dumps(source, indent=2) + '\n')
argv = [allocation['python'], '-I', '-B', str(HERE / 'fixture.py')]
record = dict(argv=argv, cwd=str(ROOT / 'cwd'), at=datetime.now(timezone.utc).isoformat(),
              setup_deadline=180, browser_deadline=180, global_deadline=480, signals=[])
known = {}
with (ROOT / 'fixture.log').open('w', encoding='utf-8') as log:
    process = subprocess.Popen(argv, cwd=ROOT / 'cwd', env=env, stdin=subprocess.PIPE,
        stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    process.stdin.close()
    started = time.monotonic()
    signaled = None
    failed_at = None
    announced = False
    while process.poll() is None:
        try:
            owner = psutil.Process(process.pid)
            for child in [owner, *owner.children(recursive=True)]:
                if child.pid not in known:
                    try:
                        known[child.pid] = dict(pid=child.pid, created=child.create_time(), exe=child.exe(),
                            argv_sha256=hashlib.sha256(' '.join(child.cmdline()).encode()).hexdigest())
                    except psutil.NoSuchProcess:
                        pass
        except psutil.NoSuchProcess:
            pass
        (ROOT / 'owned-processes.json').write_text(json.dumps(list(known.values()), indent=2) + '\n')
        ready = ROOT / 'control/ready.json'
        now = time.monotonic()
        if ready.exists() and not announced:
            value = json.loads(ready.read_text())
            print(json.dumps(dict(status='READY', url=value['url'], sessions=value['sessions'],
                                  reference=value['reference'])), flush=True)
            announced = True
        if (ROOT / 'control/blocked-operation.json').exists() and failed_at is None:
            failed_at = now
        due = now - started > 480 or not announced and now - started > 180 or failed_at is not None and now - failed_at > 30
        if due and signaled is None:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            signaled = now
            record['signals'].append('CTRL_BREAK only own dedicated process group after bounded fixture phase')
        if signaled is not None and now - signaled > 8:
            for value in reversed(list(known.values())):
                try:
                    child = psutil.Process(value['pid'])
                    if abs(child.create_time() - value['created']) < .01 and child.exe() == value['exe']:
                        child.kill()
                except psutil.NoSuchProcess:
                    pass
            record['signals'].append('Contain only exact own PID/birth/executable records after interrupt grace')
            break
        time.sleep(.2)
    process.wait(timeout=10)
remaining = []
for value in known.values():
    try:
        child = psutil.Process(value['pid'])
        if abs(child.create_time() - value['created']) < .01 and child.is_running():
            remaining.append(value)
    except psutil.NoSuchProcess:
        pass
after = payload()
after_source = builder.pins()
drift = [k for k in source.keys() | after_source.keys() if source.get(k) != after_source.get(k)]
(ROOT / 'payload-after.json').write_text(json.dumps(after, indent=2) + '\n')
record.update(exit_code=process.returncode, announced_ready=announced, remaining=remaining,
              payload_files=len(after), payload_drift=[] if before == after else ['payload_changed'], source_drift=drift,
              ended_at=datetime.now(timezone.utc).isoformat())
(ROOT / 'supervisor-result.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
assert not remaining and before == after and not drift
