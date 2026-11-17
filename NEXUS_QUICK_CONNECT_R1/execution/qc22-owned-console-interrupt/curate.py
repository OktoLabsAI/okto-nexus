"""Curate one real isolated-console interrupt, preserving exact executed scripts."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = Path(json.loads((HERE / 'allocation.json').read_text())['root'])
OUT = HERE / 'evidence'
OUT.mkdir(exist_ok=False)
result = json.loads((ROOT / 'result.json').read_text())
assert result['status'] == 'PASS' and result['failure'] is None and not result['containment']
assert result['payload_files'] == 1027 and result['payload_drift'] == result['source_drift'] == []
assert all(not process['alive'] for process in result['process_proofs'])
for name in ('win.py', 'child.py', 'controller.py', 'result.json', 'source-pins.json', 'pytest.ini',
        'child-ready.json', 'child-result.json', 'controller-started.json', 'controller-result.json',
        'permit.json', 'origins.json', 'console-proof-before-input.json', 'console-proof-before-signal.json',
        'input-intent.json', 'input-result.json', 'signal-intent.json', 'signal-result.json',
        'junit.xml', 'reports.jsonl', 'child.log', 'controller.log'):
    shutil.copyfile(ROOT / name, OUT / name)
counts = dict(tests=0, failures=0, errors=0, skipped=0)
for suite in ET.parse(OUT / 'junit.xml').getroot().iter('testsuite'):
    for key in counts:
        counts[key] += int(suite.attrib.get(key, '0'))
assert counts == dict(tests=1, failures=0, errors=0, skipped=0)
ready = json.loads((OUT / 'child-ready.json').read_text())
assert ready['stdin_isatty'] and not ready['window']['visible']
assert json.loads((OUT / 'signal-result.json').read_text())['sent'] is True
signal = json.loads((OUT / 'signal-intent.json').read_text())
assert signal['event'] == 'CTRL_C_EVENT' and signal['group'] == 0 and signal['exactly_one_attempt']
assert json.loads((OUT / 'input-result.json').read_text())['records_written'] == 4
members = json.loads((OUT / 'console-proof-before-signal.json').read_text())
assert set(signal['members']) == set(members['members'])
assert not members['window']['visible']
owned = {row['pid']: row for row in json.loads((OUT / 'permit.json').read_text())['owned_processes']}
assert set(members['members']) <= set(owned)
assert ready['pid'] in members['members']
for proof in members['proofs']:
    assert proof['birth_filetime'] == owned[proof['pid']]['birth_filetime']
    assert proof['image'].casefold() == owned[proof['pid']]['image'].casefold()
hosts = sorted({row['pid'] for row in result['observed_non_clients'] if (row.get('image') or '').lower().endswith('conhost.exe')})
command = ['rtk', 'proxy', 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-Command',
    'Get-CimInstance Win32_Process -Filter "' + ' OR '.join('ProcessId=' + str(pid) for pid in hosts)
    + '" | Select-Object ProcessId,ParentProcessId,ExecutablePath | ConvertTo-Json']
check = subprocess.run(command, capture_output=True, text=True, timeout=10, check=True)
assert not check.stdout.strip(), 'Observed console host still exists; do not claim complete host cleanup'
user = ctypes.WinDLL('user32', use_last_error=True)
user.IsWindow.argtypes = [wintypes.HWND]
user.IsWindow.restype = wintypes.BOOL
assert not user.IsWindow(ready['window']['hwnd'])
cleanup = dict(observed_python_clients=result['process_proofs'], observed_console_host_pids=hosts,
    console_hosts_absent=True, console_host_check_command=command, console_host_check_exit=check.returncode,
    original_console_window_destroyed=True, containment=[], source_drift=[], payload_drift=[])
(OUT / 'cleanup.json').write_text(json.dumps(cleanup, indent=2))
report = dict(at=datetime.now(timezone.utc).isoformat(), status='PASS_OWNED_HIDDEN_WINDOWS_CONSOLE_INTERRUPT',
    counts=counts, node='test_quick_connect_pty.py::test_ctrl_c_after_issued_test_preserves_checkpoint_and_only_ends_observation',
    original_test_sha256=ready['original_test_sha256'], original_test_edited=False,
    source_commit='fa031697b37a1b879d855f7858f01320addf0df7',
    wheel_sha256='a36e448c80a8190c7e8c92d81ea5a251c4bdf7e370eca0f0b395a5ad29e36cc6',
    own_root=str(ROOT), elapsed_seconds=result['elapsed_seconds'], installed_payload_files=1027,
    installed_payload_drift=[], source_drift=[], provider_calls=0,
    console=dict(real_CONIN=True, GetConsoleMode=True, stdin_isatty=True, visible=False,
        signal_members=members['members'], owned_client_count=len(owned), ctrl_c_attempts=1,
        input_records=4, user_or_supervisor_console_attached=False),
    proofs=['A distinct hidden Windows console was created using CREATE_NEW_CONSOLE and SW_HIDE.',
        'Real CONIN$/GetConsoleMode/isatty was checked both by wrapper and pytest session audit; no stdin/isatty/input mock was used.',
        'Before y and Ctrl-C, the separate controller proved exact attached membership against parent/birth/image ownership of child/controller Python clients.',
        'The controller attached only to the owned child console, ignored Ctrl-C only for itself, and sent one console-scoped CTRL_C_EVENT only after the issued synthetic-Test marker.',
        'The unchanged original test asserts CLI130, checkpoint test_submitted, one synthetic Test/probe, no binding/grant, and explicitly releases its inert async gate before lifespan closes.',
        'Both child and controller exited zero normally; all observed Python clients and Windows console hosts are absent, and the owned console window was destroyed.'],
    prelaunch_antecedent='Missing environment parent directory caused a preparation failure before any process, console, pytest, input or signal. It was corrected before this sole pytest execution.',
    static_checks='Ruff F/E7/E9 PASS; E402 applies to the intentional -I own-script-directory bootstrap imports.',
    limitations=['This is a real isolated Windows console signal test with synthetic application setup/Test/lifecycle; not a real provider/native harness campaign.',
        'It does not exercise Ctrl-C in the user console, RTK transport, or a Windows session restart/logout/suspend.',
        'No generic kill/broadcast or unowned PID was used; zero fallback containment was required.',
        'No repository test/source/docs, installed prefix, earlier evidence, personal installation or account was modified.'])
(HERE / 'qualification.json').write_text(json.dumps(report, indent=2))
manifest = {p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in OUT.rglob('*') if p.is_file()}
for name in ('qualification.json', 'mechanism.json', 'prelaunch-antecedent.json', 'prepare.py', 'run.py', 'win.py', 'child.py', 'controller.py', 'curate.py'):
    manifest[name] = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps(dict(counts=counts, qualification_sha256=manifest['qualification.json'],
    ctrl_c_attempts=1, signal_members=members['members'], owned_python_clients=len(owned),
    observed_console_hosts_absent=hosts, containment_count=0)))
