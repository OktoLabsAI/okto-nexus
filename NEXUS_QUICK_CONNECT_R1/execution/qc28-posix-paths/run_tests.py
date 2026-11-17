"""Bounded installed Linux cuts in own process groups and directories."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import zipfile

ROOT = Path('/tmp/nexus-qc28-xmlie7rv')
REPO = Path('/mnt/d/Projetos/Techridy/okto_labs_okto_nexus')
PREFIX = ROOT / 'venv'
PYTHON = PREFIX / 'bin/python'
ENV = dict(PATH='/usr/bin:/bin', HOME=str(ROOT / 'home'), XDG_CONFIG_HOME=str(ROOT / 'xdg-config'),
    XDG_DATA_HOME=str(ROOT / 'xdg-data'), XDG_CACHE_HOME=str(ROOT / 'xdg-cache'), TMPDIR=str(ROOT / 'test-tmp'),
    LANG='C.UTF-8', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM='/dev/null', GIT_CONFIG_GLOBAL='/dev/null',
    GIT_TERMINAL_PROMPT='0', PIP_CONFIG_FILE='/dev/null')


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def payload():
    values = {}
    for wheel in (ROOT / 'wheels').glob('*.whl'):
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if name.startswith(('okto_nexus/', 'nexus_connector_core/', 'okto_nexus_connector/')) and not name.endswith('/'):
                    data = (PREFIX / 'lib/python3.13/site-packages' / name).read_bytes()
                    assert data == archive.read(name), name
                    values[name] = hashlib.sha256(data).hexdigest()
    assert len(values) == 1027
    return values


def group_members(group):
    found = []
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        try:
            parts = (path / 'stat').read_text().split(') ', 1)[1].split()
            if int(parts[2]) == group and parts[0] != 'Z':
                found.append(dict(pid=int(path.name), state=parts[0], start_ticks=parts[19]))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return found


before = payload()
write(ROOT / 'payload-before.json', before)
cases = []
names = ['test_posix_physical_paths.py', 'test_connect_arguments.py', 'test_git_project_hint.py',
         'test_git_project_trust.py', 'test_quick_connect_project.py', 'test_quick_connect_id_choices.py']
for name in names:
    out = ROOT / 'test-output' / name.removesuffix('.py')
    out.mkdir()
    env = ENV | {'QC28_OUTPUT': str(out)}
    argv = [str(PYTHON), '-I', '-B', '-m', 'pytest', '-c', str(ROOT / 'pytest.ini'),
        '--rootdir=' + str(ROOT / 'tests'), '--confcutdir=' + str(ROOT / 'tests'),
        str(ROOT / 'tests' / name), '-v', '-s', '-x', '--tb=short',
        '--basetemp=' + str(ROOT / 'test-tmp' / name.removesuffix('.py')),
        '--junitxml=' + str(out / 'junit.xml')]
    record = dict(name=name, argv=argv, cwd=str(ROOT / 'cwd'), env_keys=sorted(env),
        started_at=datetime.now(timezone.utc).isoformat(), deadline_seconds=180, signals=[])
    print('START ' + name, flush=True)
    with (out / 'raw.log').open('w') as log:
        process = subprocess.Popen(argv, cwd=ROOT / 'cwd', env=env, stdin=subprocess.PIPE,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        process.stdin.close()
        record['pid'] = process.pid
        try:
            process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            record['signals'].append('SIGTERM only own new process group after 180s deadline')
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
    record.update(exit_code=process.returncode, ended_at=datetime.now(timezone.utc).isoformat(),
                  remaining_process_group=group_members(process.pid))
    write(out / 'runner.json', record)
    assert not record['remaining_process_group'], record
    cases.append(record)
    print(json.dumps(dict(name=name, exit_code=process.returncode)), flush=True)
after = payload()
write(ROOT / 'payload-after.json', after)
assert before == after
pins = json.loads((ROOT / 'copied-test-pins.json').read_text())
drift = [name for name, pin in pins.items() if hashlib.sha256((REPO / name).read_bytes()).hexdigest() != pin]
assert not drift, drift
write(ROOT / 'result.json', dict(cases=cases, payload_files=1027, payload_drift=[], source_test_drift=[],
    no_src_copy=True, no_service_or_provider=True, interpreter='3.13.1', scope='Ubuntu WSL2 only, selected installed tests'))
print(json.dumps(dict(status='CUTS_COMPLETED', cases=[dict(name=r['name'], exit_code=r['exit_code']) for r in cases])), flush=True)
