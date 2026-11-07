"""Curate a closed allowlist; never copy private homes, databases or raw logs."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
PUBLIC = ROOT/'public'
PUBLIC.mkdir(exist_ok=True)
attempts = [
    ('initial', 'Fixture: launcher PID was incorrectly compared with real Server owner PID; failed before native launch.'),
    ('retry-owner', 'Collection: shared helper added psutil absent from isolated environment; no process started.'),
    ('retry-stdlib', 'Oracle: short CLI timeout honestly returned UNCONFIRMED; test prematurely required DRAINING_PENDING from that response.'),
    ('retry-canonical', 'Fixture: human operator client rejected the /v1 route before network I/O.'),
    ('retry-operator-route', 'Fixture: runtime-shutdown read did not accept human operator context; replaced by existing canonical local service inspection.'),
    ('retry-service-inspection', 'PASS: same real Server and live Core-owned Connector child while restart pending; normal terminal/close then child exit0, slot release and Server drained without replacement.'),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def copy(source, target):
    target = PUBLIC/target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    assert sha(source) == sha(target)


reports = []
for name, classification in attempts:
    source = ROOT/(name+'.xml')
    cases = ET.parse(source).findall('.//testcase')
    row = dict(report=f'reports/{name}.xml', sha256=sha(source),
               cases=len(cases), failures=sum(c.find('failure') is not None for c in cases),
               errors=sum(c.find('error') is not None for c in cases),
               skipped=sum(c.find('skipped') is not None for c in cases), classification=classification,
               product_defect_proven=False)
    row['passed'] = row['cases']-row['failures']-row['errors']-row['skipped']
    result = json.loads((ROOT/(name+'-result.json')).read_text(encoding='utf-8'))
    row['source_unchanged_during_run'] = result['unchanged']
    row['exit_code'] = result['exit_code']
    reports.append(row)
    for suffix in ('.xml','-command.json','-result.json'):
        copy(ROOT/(name+suffix), 'reports/'+name+suffix)
    snapshot = ROOT/(name+'-test.py')
    if snapshot.exists():
        copy(snapshot, 'sources/history/'+snapshot.name)
        row['test_snapshot'] = 'sources/history/'+snapshot.name

test = REPO/'tests/execution_r4/test_service_surviving_child.py'
helper = REPO/'tests/execution_r4/test_service_restart_contracts.py'
copy(test, 'sources/test_service_surviving_child.py')
copy(helper, 'sources/test_service_restart_contracts.py')
copy(ROOT/'run_source.py', 'scripts/run_source.py')
copy(ROOT/'pytest.ini', 'scripts/pytest.ini')
copy(__file__, 'scripts/curate_public.py')
final_dir = ROOT/'retry-service-inspection-private/test_restart_pending_keeps_rea0'
copy(final_dir/'owned-child-proof.json', 'owned-child-proof.json')
copy(final_dir/'owner-proofs.json', 'server-owner-proofs.json')
proof = json.loads((PUBLIC/'owned-child-proof.json').read_text(encoding='utf-8'))
assert proof['completed'] and proof['child_exit_code'] == 0
assert proof['physical_release_confirmed'] and proof['slot_after_release']['released']
assert proof['final_service_state'] == 'stopped' and not proof['automatic_replacement_started']
assert reports[-1]['passed'] == 1 and reports[-1]['exit_code'] == 0

# Observe only the two birth-fenced processes in this completed test. No signaling,
# command line enumeration, personal service access or credentials involved.
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
kernel.WaitForSingleObject.restype = wintypes.DWORD
class FileTime(ctypes.Structure):
    _fields_ = [('low',wintypes.DWORD),('high',wintypes.DWORD)]
kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *([ctypes.POINTER(FileTime)]*4))
kernel.GetProcessTimes.restype = wintypes.BOOL
server_owner = json.loads((PUBLIC/'server-owner-proofs.json').read_text(encoding='utf-8'))[0]
absence = {}
for label, pid, birth in [('server',proof['server_pid'],server_owner['birth']),
                         ('native_child',proof['birth']['evidence']['pid'],
                          int(proof['birth']['evidence']['birth_token'].split(':')[1],16))]:
    handle = kernel.OpenProcess(0x00101000, False, pid)
    if handle:
        try:
            times = [FileTime() for _ in range(4)]
            assert kernel.GetProcessTimes(handle,*(ctypes.byref(x) for x in times))
            observed_birth = (times[0].high<<32)|times[0].low
            if observed_birth == birth:
                assert kernel.WaitForSingleObject(handle,0) == 0, label
                absence[label] = dict(pid=pid, original_birth_running=False,
                                      observation='same_birth_process_signaled_exit')
            else:
                absence[label] = dict(pid=pid, original_birth_running=False,
                                      observation='pid_reused_by_different_birth')
        finally:
            kernel.CloseHandle(handle)
    else:
        error = ctypes.get_last_error()
        assert error == 87, (label, error)
        absence[label] = dict(pid=pid, original_birth_running=False,observation='pid_absent')
cleanup = dict(observed_at_utc=datetime.now(timezone.utc).isoformat(), processes=absence,
               child_exit_code=0, server_exit_code=0, source_runner_exit_code=0,
               cleanup='Exact owned handles/births only; no original owned process remains running. Runner exited0; PID presence alone is never an ownership oracle.')
(PUBLIC/'cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n',encoding='utf-8')

ruff = subprocess.run(['rtk','proxy','python','-m','ruff','check',str(test)],
                      cwd=REPO,capture_output=True,text=True,check=True)
(PUBLIC/'ruff.txt').write_text(ruff.stdout,encoding='utf-8')
diff = subprocess.run(['rtk','proxy','git','diff','--no-index','--','/dev/null',str(test)],
                      cwd=REPO,capture_output=True,text=True)
assert diff.returncode == 1
(PUBLIC/'test.patch').write_text(diff.stdout,encoding='utf-8')
(PUBLIC/'reports.json').write_text(json.dumps(dict(
    scope='SVC-T22 safe Windows restart-pending contract with one physical Core-owned Python child',
    unique_final_cases=1, unique_final_passed=1, attempts=reports,
    duplicate_count_policy='All executions are the same test identity; failures/collection errors are retained, not added to final coverage.',
    final_source_sha256=sha(test), helper_sha256=sha(helper),
    public_xml_bytes_unchanged=True, no_product_changes=True, installed_qualification='Owned by root, pending at source closure',
    limits=['Child belongs to Core in Connector, not to Server.',
            'Restart remained pending; no completed replacement while child was alive is claimed.',
            'No survival after parent death is claimed; Job containment was not weakened.',
            'No provider/native-service/task/personal credential campaign.']),indent=2)+'\n',encoding='utf-8')

# Credential-shaped values are not expected in this explicit allowlist. Report
# filenames only on a failure; never print matching content.
patterns = [rb'Bearer\s+[A-Za-z0-9_-]{24,}', rb'nk_[A-Za-z0-9_-]{24,}',
            rb'nxa_[A-Za-z0-9_-]{24,}', rb'api_key[\"\x27]\s*:\s*[\"\x27][A-Za-z0-9_-]{24,}']
for path in PUBLIC.rglob('*'):
    if path.is_file() and path.name != 'curate_public.py':
        assert not any(re.search(pattern,path.read_bytes()) for pattern in patterns), path.name
files = {p.relative_to(PUBLIC).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
         for p in sorted(PUBLIC.rglob('*')) if p.is_file() and p.name!='manifest.json'}
(PUBLIC/'manifest.json').write_text(json.dumps(dict(files=files, allowlist_only=True,
    excluded=['private profiles','DB/WAL/SHM','raw process logs','vault files','credential material'],
    final_source_sha256=sha(test), files_count=len(files)),indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(public=str(PUBLIC),files=len(files),manifest_sha256=sha(PUBLIC/'manifest.json'),
                     final_xml_sha256=sha(ROOT/'retry-service-inspection.xml'),cleanup=absence)))
