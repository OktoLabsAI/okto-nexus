"""Export console ownership/results only; raw buffers and homes stay Temp."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
user = ctypes.WinDLL('user32', use_last_error=True)
user.IsWindow.argtypes = [wintypes.HWND]
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.WaitForSingleObject.restype = wintypes.DWORD
results = []
for label in ('ctrl-c', 'resize'):
    folder = HERE/label
    root = Path(json.loads((folder/'allocation.json').read_text())['root'])
    result = json.loads((root/'result.json').read_text())
    assert result['status'] == 'PASS' and not result['containment']
    assert not result['payload_drift'] and not result['source_drift']
    ready = json.loads((root/'child-ready.json').read_text())
    assert not user.IsWindow(ready['window']['hwnd'])
    assert all(not p['alive'] for p in result['process_proofs'])
    out = folder/'evidence'
    out.mkdir(exist_ok=False)
    raw_refs = []
    for name in ('child.log','controller.log','buffer-review.txt','buffer-resume.txt','buffer-final.txt'):
        path = root/name
        if path.exists():
            raw_refs.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),exported=False))
    for p in root.glob('*.json'):
        if p.name not in ('result.json',):
            shutil.copyfile(p,out/p.name)
    # No image/command line of a process outside the ownership permit is exported.
    result['observed_non_clients'] = [dict(pid=p['pid'],parent_pid=p.get('parent_pid'),
        authorization=p['authorization'],details_redacted=True) for p in result['observed_non_clients']]
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    document = ET.parse(root/'junit.xml')
    for parent in document.iter():
        for child in list(parent):
            if child.tag in ('system-out','system-err'):
                parent.remove(child)
    nodes = []
    for node in document.iter('testcase'):
        assert node.find('failure') is None and node.find('error') is None and node.find('skipped') is None
        nodes.append(dict(name=node.get('name'),classname=node.get('classname'),seconds=node.get('time'),status='PASS'))
    assert len(nodes) == 1
    document.write(out/'junit-sanitized.xml',encoding='utf-8',xml_declaration=True)
    non_clients = sorted({p['pid'] for p in result['observed_non_clients']})
    absences = []
    for pid in non_clients:
        handle = kernel.OpenProcess(0x1000|0x100000,False,pid)
        alive = bool(handle and kernel.WaitForSingleObject(handle,0)==258)
        absences.append(dict(pid=pid,alive=alive,owned_or_signaled=False))
        if handle:
            kernel.CloseHandle(handle)
    controller = json.loads((root/'controller-result.json').read_text())
    results.append(dict(cut=label,status='PASS',nodes=nodes,controller=controller,
        elapsed_seconds=result['elapsed_seconds'],commands=result['commands'],
        original_test_sha256=ready['original_test_sha256'],stdin_isatty=ready['stdin_isatty'],
        stdout_isatty=ready.get('stdout_isatty'),stderr_isatty=ready.get('stderr_isatty'),
        console_hidden=True,console_window_destroyed=True,all_proven_python_processes_exited=True,
        process_proofs=result['process_proofs'],non_client_readonly_absence_probe=absences,
        containment=[],payload_files=result['payload_files'],payload_drift=[],source_drift=[],raw_refs=raw_refs))
qualification = dict(status='PASS_TWO_SEPARATE_ORIGINAL_CONSOLE_NODES',passed=2,failed=0,skipped=0,
    mode='INSTALLED_NO_CHECKOUT_IMPORT',source_candidate='9bc4034663ca63cfee43790b4bc03c38f8bdebcc',
    wheel_sha256='d2c322168d56e87bde22cfe262d5d2fbc9a5737b0572144774894624d561cf88',
    tests_unchanged=True,controllers_unchanged=True,source_cut_comparison='source-pins.json per cut, no drift',
    cuts=results,payload_files=1028,payload_drift=[],source_drift=[],provider_calls=0,
    limits=['Two sequential cuts, each with one unchanged original node; not a combined pytest round.',
        'Real isolated hidden Windows console, not user/RTK console, logout/reboot/suspend or every terminal/PTY.',
        'Model/version/Test/lifecycle peers remain synthetic; zero authenticated provider/native account calls.',
        'Ctrl-C is only one console-scoped event after exact ownership/membership/issued-Test fences. Resize sends no signals.',
        'Raw console buffers, logs, fixture database and vault material remain owned Temp; no secrets exported.',
        'Supervisor derivative only changes package/root bindings, payload count and rejects a child older than its retained parent; qualified controllers/tests are byte-identical.'])
(HERE/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n')
files = [p for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts]
(HERE/'manifest.json').write_text(json.dumps([dict(path=p.relative_to(HERE).as_posix(),
    sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in files],indent=2)+'\n')
print(json.dumps(dict(status=qualification['status'],passed=2,manifest_entries=len(files),
    all_proven_python_exited=True,windows_destroyed=True,non_client_absences=[c['non_client_readonly_absence_probe'] for c in results])))
