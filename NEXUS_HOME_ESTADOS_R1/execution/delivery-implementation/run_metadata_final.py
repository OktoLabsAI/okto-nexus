"""Finite SOURCE_ONLY qualification; PR27 supplies dependencies, never product.

No pip/build/provider execution. All runtime homes are disposable. Raw fixture
outputs stay in own Temp; only sanitized qualification/evidence is exported.
"""
from datetime import datetime, timezone
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PREFIX = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r3-harness-pr27-gsg_twh1/venv')
PYTHON = PREFIX / 'Scripts/python.exe'
OWN = Path(tempfile.mkdtemp(prefix='nexus-hst-delivery-source-')).resolve()
(HERE / 'metadata-final-allocation.json').write_text(json.dumps({'root': str(OWN), 'mode': 'SOURCE_ONLY'}, indent=2))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def pins():
    return {p.relative_to(REPO).as_posix(): sha(p) for folder in ('src', 'tests')
            for p in (REPO / folder).rglob('*') if p.is_file()
            and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}

def payload():
    result = {}
    wheels = [('okto_nexus', PREFIX.parent / 'final/artifacts/okto_nexus-0.3.5-py3-none-any.whl'),
              ('nexus_connector_core', REPO / 'vendor/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl'),
              ('okto_nexus_connector', REPO / 'vendor/ci/okto_nexus_connector-0.0.13-py3-none-any.whl')]
    for package, wheel in wheels:
        with zipfile.ZipFile(wheel) as z:
            for name in z.namelist():
                if name.startswith(package + '/') and not name.endswith('/'):
                    data = (PREFIX / 'Lib/site-packages' / name).read_bytes()
                    assert data == z.read(name), name
                    result[name] = hashlib.sha256(data).hexdigest()
    return result

def environment(out):
    allowed = {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'NUMBER_OF_PROCESSORS',
               'PROCESSOR_ARCHITECTURE', 'SYSTEMDRIVE', 'OS', 'PROGRAMFILES', 'PROGRAMFILES(X86)'}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    for key, name in [('HOME', 'user'), ('USERPROFILE', 'user'), ('APPDATA', 'appdata'),
                      ('LOCALAPPDATA', 'localappdata'), ('TEMP', 'tmp'), ('TMP', 'tmp')]:
        (out / name).mkdir(exist_ok=True)
        env[key] = str(out / name)
    env.update(PATH=';'.join([str(PREFIX/'Scripts'), 'C:/Python313', 'C:/Windows/System32',
                            'C:/Windows', 'C:/Program Files/Git/cmd', 'C:/Program Files/nodejs']),
               PYTHONUTF8='1', PIP_CONFIG_FILE=os.devnull, UV_NO_CONFIG='1',
               GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=os.devnull,
               GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0', QC_DERIVATIVE_OUTPUT=str(out))
    return env

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
kernel.GetProcessTimes.restype = wintypes.BOOL
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.WaitForSingleObject.restype = wintypes.DWORD
kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel.TerminateProcess.restype = wintypes.BOOL
kernel.CloseHandle.argtypes = [wintypes.HANDLE]

class Owned:
    def __init__(self, pid, parent=None):
        self.pid, self.parent = pid, parent
        self.handle = kernel.OpenProcess(0x1000 | 0x100000 | 0x1, False, pid)
        if not self.handle:
            raise ProcessLookupError(pid)
        times = [wintypes.FILETIME() for _ in range(4)]
        assert kernel.GetProcessTimes(self.handle, *map(ctypes.byref, times))
        self.birth = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    def alive(self):
        return kernel.WaitForSingleObject(self.handle, 0) == 258
    def facts(self):
        return dict(pid=self.pid, parent_pid=self.parent, birth_filetime=self.birth, alive=self.alive())

plugin = '''import importlib.util,json,pathlib,sys,re,os
import pytest
OUT=pathlib.Path(os.environ['QC_DERIVATIVE_OUTPUT'])
SRC=pathlib.Path(%r).resolve()
PREFIX=pathlib.Path(%r).resolve()
def check(label):
    origins={n:importlib.util.find_spec(n).origin for n in ('okto_nexus','nexus_connector_core','okto_nexus_connector')}
    assert pathlib.Path(origins['okto_nexus']).resolve().is_relative_to(SRC)
    assert all(pathlib.Path(origins[n]).resolve().is_relative_to(PREFIX) for n in ('nexus_connector_core','okto_nexus_connector'))
    invalid={n:getattr(m,'__file__',None) for n,m in list(sys.modules.items()) if getattr(m,'__file__',None) and ((n=='okto_nexus' or n.startswith('okto_nexus.')) and not pathlib.Path(m.__file__).resolve().is_relative_to(SRC) or (n=='nexus_connector_core' or n.startswith('nexus_connector_core.') or n=='okto_nexus_connector' or n.startswith('okto_nexus_connector.')) and not pathlib.Path(m.__file__).resolve().is_relative_to(PREFIX))}
    assert not invalid,invalid
    (OUT/('origins-'+label+'.json')).write_text(json.dumps(dict(mode='SOURCE_ONLY',origins=origins,invalid=invalid,sys_path=sys.path),indent=2))
def pytest_sessionstart(session): check('start')
def pytest_sessionfinish(session,exitstatus): check('finish')
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    outcome=yield
    r=outcome.get_result()
    value=dict(nodeid=r.nodeid,when=r.when,outcome=r.outcome,duration=r.duration)
    if r.failed:
        value['failure']=re.sub(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+','<ephemeral-token-redacted>',r.longreprtext)
    with (OUT/'reports.jsonl').open('a') as stream: stream.write(json.dumps(value)+'\\n')
    print('QC38_REPORT '+json.dumps(value),flush=True)
''' % (str(REPO/'src'), str(PREFIX))
(OWN/'qc38_plugin.py').write_text(plugin, encoding='utf-8')
bootstrap = '''import sys,pytest
sys.path[:0]=%r
raise SystemExit(pytest.main(sys.argv[1:]))
''' % [str(REPO/'src'), str(REPO/'tests'), str(REPO/'tests/execution_r4'), str(REPO/'tests/quick_connect'), str(OWN)]
(OWN/'bootstrap.py').write_text(bootstrap, encoding='utf-8')
(OWN/'pytest.ini').write_text('[pytest]\naddopts =\n', encoding='utf-8')
before_pins, before_payload = pins(), payload()
(OWN/'source-pins-start.json').write_text(json.dumps(before_pins, indent=2))
(OWN/'payload-start.json').write_text(json.dumps(before_payload, indent=2))
cases = [('domain', 'tests/home_states/test_delivery_semantics.py', []), ('verification', 'tests/home_states/test_verification_proof.py', []), ('standalone-sqlite', 'tests/home_states/test_delivery_semantics_sqlite.py', []), ('legacy-result-artifacts', 'tests/home_evolution/test_home_result_artifact_grouping.py', []), ('legacy-home-queries', 'tests/home_evolution/test_home_queries.py', []), ('canonical-verification', 'tests/test_verification.py', ['-k', 'test_ts4_complete_with_criteria_parks_in_verifying or test_ts5_verify_pass_completes_with_verified_by_on_the_canonical_event or test_ts6_verify_fail_drives_rework_cycles_with_renewed_lease'])]
rtk = shutil.which('rtk')
records = []
for label, node, extra in cases:
    out = OWN / label
    out.mkdir()
    (out/'cwd').mkdir()
    env = environment(out)
    command = [str(PYTHON), '-I', '-B', str(OWN/'bootstrap.py'), '-p', 'qc38_plugin',
               '-c', str(OWN/'pytest.ini'), '--rootdir='+str(REPO), '--confcutdir='+str(REPO),
               str(REPO/node), '-v', '-s', '-o', 'faulthandler_timeout=0', '--tb=short', '--junitxml='+str(out/'junit.xml'), *extra]
    record = dict(label=label, argv=command, cwd=str(out/'cwd'), deadline_seconds=180,
                  started_at=datetime.now(timezone.utc).isoformat(), signals=[])
    (out/'runner-start.json').write_text(json.dumps(record, indent=2))
    known = {}
    rejected = []
    with (out/'raw.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=out/'cwd', env=env, stdin=subprocess.PIPE,
            stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        process.stdin.close()
        known[process.pid] = Owned(process.pid)
        print(json.dumps(dict(start=label, pid=process.pid, mode='SOURCE_ONLY')), flush=True)
        deadline, last_scan, signaled = time.monotonic()+180, 0, None
        while process.poll() is None:
            now = time.monotonic()
            if now-last_scan >= 2:
                alive = [p for p, item in known.items() if item.alive()]
                if alive:
                    query = ' OR '.join('ParentProcessId='+str(p) for p in alive)
                    ps = 'Get-CimInstance Win32_Process -Filter "'+query+'" | Select-Object ProcessId,ParentProcessId | ConvertTo-Json'
                    scan = subprocess.run([rtk, 'proxy', 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-Command', ps], cwd=out, env=env, capture_output=True, text=True, timeout=8)
                    if scan.stdout.strip():
                        rows = json.loads(scan.stdout)
                        for child in rows if isinstance(rows, list) else [rows]:
                            parent = known.get(child['ParentProcessId'])
                            if parent and parent.alive() and child['ProcessId'] not in known:
                                try:
                                    item = Owned(child['ProcessId'], parent.pid)
                                except ProcessLookupError:
                                    continue
                                if item.birth < parent.birth:
                                    rejected.append(dict(pid=item.pid, birth=item.birth, parent_birth=parent.birth))
                                    kernel.CloseHandle(item.handle)
                                else:
                                    known[item.pid] = item
                last_scan = now
            if now >= deadline and signaled is None:
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                    record['signals'].append('CTRL_BREAK own new process group at deadline')
                except OSError:
                    record['signals'].append('CTRL_BREAK unavailable')
                signaled = now
            if signaled is not None and now-signaled >= 5:
                record['before_containment'] = [item.facts() for item in known.values()]
                for item in reversed(list(known.values())):
                    if item.alive():
                        assert kernel.TerminateProcess(item.handle, 124)
                record['signals'].append('TerminateProcess exact retained own handles only')
                process.wait(timeout=10)
                break
            time.sleep(.1)
        process.wait(timeout=1)
    for item in known.values():
        if item.alive():
            kernel.WaitForSingleObject(item.handle, 5000)
    record.update(exit_code=process.returncode, processes_after=[item.facts() for item in known.values()],
                  rejected_nonowned_births=rejected, ended_at=datetime.now(timezone.utc).isoformat())
    (out/'runner.json').write_text(json.dumps(record, indent=2))
    assert all(not item['alive'] for item in record['processes_after'])
    for item in known.values():
        kernel.CloseHandle(item.handle)
    records.append(record)
    print(json.dumps(dict(finish=label, exit_code=process.returncode, signals=record['signals'])), flush=True)
after_pins, after_payload = pins(), payload()
drift = [n for n in before_pins.keys() | after_pins.keys() if before_pins.get(n) != after_pins.get(n)]
(OWN/'source-pins-end.json').write_text(json.dumps(after_pins, indent=2))
(OWN/'payload-end.json').write_text(json.dumps(after_payload, indent=2))
result = dict(mode='SOURCE_ONLY_NOT_NEW_INSTALLED_PACKAGE', cases=records,
    payload_files=len(before_payload), payload_drift=[n for n in before_payload if before_payload[n]!=after_payload.get(n)],
    repository_input_drift=drift, runtime_root=str(OWN), provider_calls=0)
(OWN/'result.json').write_text(json.dumps(result, indent=2))
print(json.dumps(dict(root=str(OWN), cases=[dict(label=r['label'], exit_code=r['exit_code']) for r in records],
                     payload_files=len(before_payload), source_drift=drift)), flush=True)
